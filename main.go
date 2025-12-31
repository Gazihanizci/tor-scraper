// main.go
package main

import (
	"bufio"
	"context"
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"golang.org/x/net/proxy"
)

type Config struct {
	TargetsPath       string
	OutDir            string
	ProxyAddr         string
	Timeout           time.Duration
	Workers           int
	CheckTor          bool
	TakeScreenshots   bool
	ScreenshotTimeout time.Duration
	ScreenshotWaitMS  int
}

type ScanResult struct {
	URL             string `json:"url"`
	Normalized      string `json:"normalized_url"`
	Active          bool   `json:"active"`
	HTTPStatus      int    `json:"http_status,omitempty"`
	Error           string `json:"error,omitempty"`
	SavedHTML       string `json:"saved_html,omitempty"`
	SavedScreenshot string `json:"saved_screenshot,omitempty"`
	ScreenshotError string `json:"screenshot_error,omitempty"`
	TimestampUTC    string `json:"timestamp_utc"`
	DurationMS      int64  `json:"duration_ms"`
}

func main() {
	cfg := parseFlags()

	// Output directories
	htmlDir := filepath.Join(cfg.OutDir, "html")
	shotDir := filepath.Join(cfg.OutDir, "screenshots")

	if err := os.MkdirAll(htmlDir, 0755); err != nil {
		fmt.Println("[FATAL] output dir create failed:", err)
		os.Exit(1)
	}
	if cfg.TakeScreenshots {
		if err := os.MkdirAll(shotDir, 0755); err != nil {
			fmt.Println("[FATAL] screenshots dir create failed:", err)
			os.Exit(1)
		}
	}

	logPath := filepath.Join(cfg.OutDir, "scan_report.log")
	summaryPath := filepath.Join(cfg.OutDir, "scan_summary.log")
	jsonPath := filepath.Join(cfg.OutDir, "scan_results.json")

	// Read targets
	targets, err := readTargets(cfg.TargetsPath)
	if err != nil {
		fmt.Println("[FATAL] targets read failed:", err)
		os.Exit(1)
	}
	if len(targets) == 0 {
		fmt.Println("[FATAL] no targets found in", cfg.TargetsPath)
		os.Exit(1)
	}

	// Tor SOCKS5 HTTP client
	client, err := torHTTPClient(cfg.ProxyAddr, cfg.Timeout)
	if err != nil {
		fmt.Println("[FATAL] tor client init failed:", err)
		os.Exit(1)
	}

	// Optional Tor verification (for report proof)
	if cfg.CheckTor {
		ok := checkTor(client, logPath)
		if !ok {
			fmt.Println("[WARN] Tor check failed. Continue anyway (you may not be using Tor).")
		}
	}

	fmt.Printf("[INFO] Loaded %d targets\n", len(targets))
	fmt.Printf("[INFO] Proxy: %s | Timeout: %s | Workers: %d | Screenshots: %v\n",
		cfg.ProxyAddr, cfg.Timeout, cfg.Workers, cfg.TakeScreenshots)
	fmt.Printf("[INFO] Output: %s\n", cfg.OutDir)

	start := time.Now()
	results := runScanPool(cfg, client, targets, htmlDir, shotDir, logPath)

	// Write JSON results
	if err := writeJSON(jsonPath, results); err != nil {
		fmt.Println("[WARN] could not write JSON results:", err)
	}

	// Write summary log
	if err := writeSummary(summaryPath, results); err != nil {
		fmt.Println("[WARN] could not write summary log:", err)
	}

	fmt.Printf("[DONE] Scan finished in %s\n", time.Since(start).Round(time.Second))
	fmt.Printf("[DONE] Report: %s\n", logPath)
	fmt.Printf("[DONE] Summary: %s\n", summaryPath)
	fmt.Printf("[DONE] JSON: %s\n", jsonPath)
}

// -------------------------
// Flags / Config
// -------------------------

func parseFlags() Config {
	var cfg Config
	flag.StringVar(&cfg.TargetsPath, "targets", "targets.yaml", "Path to targets file (one URL per line)")
	flag.StringVar(&cfg.OutDir, "out", "output", "Output directory")
	flag.StringVar(&cfg.ProxyAddr, "proxy", "127.0.0.1:9150", "SOCKS5 proxy address (Tor Browser usually 127.0.0.1:9150)")
	flag.DurationVar(&cfg.Timeout, "timeout", 30*time.Second, "HTTP request timeout")
	flag.IntVar(&cfg.Workers, "workers", 5, "Concurrent workers (use 1 for sequential)")
	flag.BoolVar(&cfg.CheckTor, "check-tor", true, "Verify Tor via https://check.torproject.org/")

	// NEW: screenshot flags
	flag.BoolVar(&cfg.TakeScreenshots, "screenshot", true, "Take screenshot (PNG) of successful pages into output/screenshots")
	flag.DurationVar(&cfg.ScreenshotTimeout, "screenshot-timeout", 25*time.Second, "Screenshot navigation/render timeout")
	flag.IntVar(&cfg.ScreenshotWaitMS, "screenshot-wait-ms", 800, "Wait after page load (ms) before taking screenshot")

	flag.Parse()

	if cfg.Workers < 1 {
		cfg.Workers = 1
	}
	return cfg
}

// -------------------------
// Input Handler
// -------------------------

func readTargets(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var out []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		// allow yaml style "- http://...."
		line = strings.TrimPrefix(line, "-")
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		out = append(out, line)
	}
	return out, sc.Err()
}

// -------------------------
// Tor Proxy Client
// -------------------------

func torHTTPClient(proxyAddr string, timeout time.Duration) (*http.Client, error) {
	dialer, err := proxy.SOCKS5("tcp", proxyAddr, nil, proxy.Direct)
	if err != nil {
		return nil, err
	}

	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		DisableKeepAlives: false,
	}

	return &http.Client{
		Transport: transport,
		Timeout:   timeout,
	}, nil
}

// -------------------------
// Tor Check (Proof for report)
// -------------------------

func checkTor(client *http.Client, logPath string) bool {
	url := "https://check.torproject.org/"
	fmt.Println("[INFO] Tor check:", url)

	resp, err := client.Get(url)
	if err != nil {
		logLine(logPath, fmt.Sprintf("[ERR ] TorCheck %s -> %v", url, err))
		return false
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	ok := strings.Contains(strings.ToLower(string(body)), "congratulations") ||
		strings.Contains(strings.ToLower(string(body)), "you are using tor")

	logLine(logPath, fmt.Sprintf("[INFO] TorCheck %s -> %s (ok=%v)", url, resp.Status, ok))
	fmt.Println("[INFO] Tor check status:", resp.Status, "ok=", ok)
	return ok
}

// -------------------------
// Scan Orchestrator (Workers)
// -------------------------

func runScanPool(cfg Config, client *http.Client, targets []string, htmlDir, shotDir, logPath string) []ScanResult {
	type job struct{ url string }

	jobs := make(chan job)
	resultsCh := make(chan ScanResult, cfg.Workers)

	var wg sync.WaitGroup

	workerFn := func(id int) {
		defer wg.Done()
		for j := range jobs {
			start := time.Now()
			normalized := normalizeURL(j.url)

			status, savedHTML, err := fetchAndSaveHTML(client, normalized, htmlDir)
			dur := time.Since(start)

			res := ScanResult{
				URL:          j.url,
				Normalized:   normalized,
				Active:       err == nil,
				HTTPStatus:   status,
				SavedHTML:    savedHTML,
				TimestampUTC: time.Now().UTC().Format(time.RFC3339),
				DurationMS:   dur.Milliseconds(),
			}

			if err != nil {
				res.Error = err.Error()
				msg := fmt.Sprintf("[W%02d][ERR ] %s -> %v", id, normalized, err)
				fmt.Println(msg)
				logLine(logPath, msg)
				resultsCh <- res
				continue
			}

			// Success log
			msg := fmt.Sprintf("[W%02d][OK  ] %s -> %d saved=%s (%dms)", id, normalized, status, savedHTML, res.DurationMS)
			fmt.Println(msg)
			logLine(logPath, msg)

			// NEW: Screenshot on success
			if cfg.TakeScreenshots {
				shotPath := makeScreenshotPath(shotDir, normalized)
				if err := captureScreenshotTor(normalized, shotPath, cfg.ProxyAddr, cfg.ScreenshotTimeout, cfg.ScreenshotWaitMS); err != nil {
					res.ScreenshotError = err.Error()
					warn := fmt.Sprintf("[W%02d][WARN] Screenshot failed: %s -> %v", id, normalized, err)
					fmt.Println(warn)
					logLine(logPath, warn)
				} else {
					res.SavedScreenshot = shotPath
					okmsg := fmt.Sprintf("[W%02d][OK  ] Screenshot saved: %s", id, shotPath)
					fmt.Println(okmsg)
					logLine(logPath, okmsg)
				}
			}

			resultsCh <- res
		}
	}

	wg.Add(cfg.Workers)
	for i := 0; i < cfg.Workers; i++ {
		go workerFn(i + 1)
	}

	go func() {
		for _, t := range targets {
			jobs <- job{url: t}
		}
		close(jobs)
	}()

	go func() {
		wg.Wait()
		close(resultsCh)
	}()

	var results []ScanResult
	for r := range resultsCh {
		results = append(results, r)
	}
	return results
}

// -------------------------
// HTML Fetcher (Request + Output Writer)
// -------------------------

func normalizeURL(url string) string {
	url = strings.TrimSpace(url)
	if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
		url = "http://" + url
	}
	return url
}

// fetchAndSaveHTML returns (httpStatus, savedHTMLPath, error)
func fetchAndSaveHTML(client *http.Client, url, htmlDir string) (int, string, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return 0, "", err
	}
	req.Header.Set("User-Agent", "TOR-Scraper/1.0 (Go)")

	resp, err := client.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()

	status := resp.StatusCode

	if status < 200 || status >= 300 {
		_, _ = io.CopyN(io.Discard, resp.Body, 4096)
		return status, "", fmt.Errorf("http status %d", status)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return status, "", err
	}

	ts := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("%s_%s.html", safeFileNameFromURL(url), ts)
	outPath := filepath.Join(htmlDir, filename)

	if err := os.WriteFile(outPath, body, 0644); err != nil {
		return status, "", err
	}
	return status, outPath, nil
}

// -------------------------
// Screenshot (chromedp)
// -------------------------

func makeScreenshotPath(shotDir, url string) string {
	ts := time.Now().Format("20060102_150405")
	name := fmt.Sprintf("%s_%s.png", safeFileNameFromURL(url), ts)
	return filepath.Join(shotDir, name)
}

// captureScreenshotTor navigates to url in headless Chrome using Tor SOCKS5 proxy and saves a full-page PNG.
func captureScreenshotTor(url, outPath, socks5Addr string, timeout time.Duration, waitMS int) error {
	// Chrome proxy syntax: socks5://host:port
	proxyArg := "--proxy-server=socks5://" + socks5Addr

	allocOpts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.Flag("headless", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("ignore-certificate-errors", true),
		chromedp.WindowSize(1366, 768),
		chromedp.Flag("disable-dev-shm-usage", true),
		chromedp.Flag("hide-scrollbars", false),
		chromedp.Flag("mute-audio", true),
		chromedp.Flag("disable-background-networking", true),
		chromedp.Flag("disable-default-apps", true),
		chromedp.Flag("disable-sync", true),
		chromedp.Flag("metrics-recording-only", true),
		chromedp.Flag("safebrowsing-disable-auto-update", true),
		chromedp.Flag("disable-extensions", true),
		chromedp.Flag("disable-popup-blocking", true),
		chromedp.Flag("disable-features", "TranslateUI"),
		chromedp.Flag("blink-settings", "imagesEnabled=true"),
		chromedp.Flag("proxy-bypass-list", "<-loopback>"),
		chromedp.Flag("disable-web-security", true),
		chromedp.Flag("allow-running-insecure-content", true),
		chromedp.Flag("disable-site-isolation-trials", true),
		chromedp.Flag("disable-features", "IsolateOrigins,site-per-process"),
		chromedp.Flag("enable-features", "NetworkService,NetworkServiceInProcess"),
		chromedp.Flag("proxy-pac-url", ""),
		chromedp.Flag("proxy-auto-detect", false),
		chromedp.Flag("enable-automation", false),
		chromedp.Flag("disable-infobars", true),
		chromedp.Flag("password-store", "basic"),
		chromedp.Flag("use-mock-keychain", true),
		chromedp.Flag("remote-debugging-port", 0),
		chromedp.Flag("disable-renderer-backgrounding", true),
		chromedp.Flag("disable-background-timer-throttling", true),
		chromedp.Flag("disable-client-side-phishing-detection", true),
		chromedp.Flag("disable-component-update", true),
		chromedp.Flag("disable-domain-reliability", true),
		chromedp.Flag("disable-print-preview", true),
		chromedp.Flag("disable-hang-monitor", true),
		chromedp.Flag("disable-prompt-on-repost", true),
		chromedp.Flag("disable-ipc-flooding-protection", true),
		chromedp.Flag("disable-notifications", true),
		chromedp.Flag("disable-translate", true),
		chromedp.Flag("proxy-server", ""), // ensure no duplicate
		chromedp.Flag("proxy-server", ""), // harmless
	)

	// put proxyArg as raw arg to avoid any ambiguity
	allocOpts = append(allocOpts, chromedp.ExecPath(findChrome()))
	allocCtx, cancel := chromedp.NewExecAllocator(context.Background(), append(allocOpts, chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""), chromedp.Flag("proxy-server", ""))...)
	_ = proxyArg // keep for clarity; actual arg below

	// NOTE: simplest reliable way: pass proxyArg using chromedp.ExecAllocator with chromedp.Flag is finicky across versions
	// so we create a new allocator again with proxyArg as a raw option:
	cancel()
	allocCtx, cancel = chromedp.NewExecAllocator(context.Background(),
		append(chromedp.DefaultExecAllocatorOptions[:],
			chromedp.Flag("headless", true),
			chromedp.Flag("disable-gpu", true),
			chromedp.Flag("no-sandbox", true),
			chromedp.Flag("ignore-certificate-errors", true),
			chromedp.WindowSize(1366, 768),
			chromedp.UserAgent("TOR-Scraper/1.0 (Go)"),
			chromedp.Flag("proxy-server", "socks5://"+socks5Addr),
		)...,
	)
	defer cancel()

	ctx, cancelCtx := chromedp.NewContext(allocCtx)
	defer cancelCtx()

	ctx, cancelTimeout := context.WithTimeout(ctx, timeout)
	defer cancelTimeout()

	var buf []byte
	err := chromedp.Run(ctx,
		chromedp.Navigate(url),
		// biraz render bekle
		chromedp.Sleep(time.Duration(waitMS)*time.Millisecond),
		chromedp.ActionFunc(func(ctx context.Context) error {
			var err error
			buf, err = page.CaptureScreenshot().WithFormat(page.CaptureScreenshotFormatPng).WithFromSurface(true).Do(ctx)
			return err
		}),
	)
	if err != nil {
		return err
	}

	return os.WriteFile(outPath, buf, 0644)
}

// findChrome: Windows'ta chromedp genelde otomatik bulur. Bu fonksiyon boş dönebilir.
// İstersen burayı sabitleyebilirsin (Chrome/Edge yolu).
func findChrome() string { return "" }

// -------------------------
// Output Writers (JSON + Summary)
// -------------------------

func writeJSON(path string, results []ScanResult) error {
	tmp := path + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	defer f.Close()

	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	if err := enc.Encode(results); err != nil {
		return err
	}
	_ = f.Close()
	return os.Rename(tmp, path)
}

func writeSummary(path string, results []ScanResult) error {
	var active, passive int
	var activeList, passiveList []string

	for _, r := range results {
		if r.Active {
			active++
			line := fmt.Sprintf("%s (%d) -> html=%s", r.Normalized, r.HTTPStatus, r.SavedHTML)
			if r.SavedScreenshot != "" {
				line += " screenshot=" + r.SavedScreenshot
			}
			if r.ScreenshotError != "" {
				line += " screenshot_error=" + r.ScreenshotError
			}
			activeList = append(activeList, line)
		} else {
			passive++
			passiveList = append(passiveList, fmt.Sprintf("%s -> %s", r.Normalized, r.Error))
		}
	}

	var b strings.Builder
	b.WriteString("=== Scan Summary ===\n")
	b.WriteString(fmt.Sprintf("Timestamp (UTC): %s\n", time.Now().UTC().Format(time.RFC3339)))
	b.WriteString(fmt.Sprintf("Total: %d | Active: %d | Passive: %d\n\n", len(results), active, passive))

	b.WriteString("== Active URLs ==\n")
	if len(activeList) == 0 {
		b.WriteString("(none)\n")
	} else {
		for _, s := range activeList {
			b.WriteString("- " + s + "\n")
		}
	}

	b.WriteString("\n== Passive URLs ==\n")
	if len(passiveList) == 0 {
		b.WriteString("(none)\n")
	} else {
		for _, s := range passiveList {
			b.WriteString("- " + s + "\n")
		}
	}

	return os.WriteFile(path, []byte(b.String()), 0644)
}

// -------------------------
// Logging
// -------------------------

func logLine(logPath, msg string) {
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Println("[WARN] log write failed:", err)
		return
	}
	defer f.Close()

	ts := time.Now().Format(time.RFC3339)
	_, _ = f.WriteString(ts + " " + msg + "\n")
}

// -------------------------
// Helpers
// -------------------------

var reBad = regexp.MustCompile(`[^\w\-.]+`)

func safeFileNameFromURL(u string) string {
	s := u
	s = strings.TrimPrefix(s, "http://")
	s = strings.TrimPrefix(s, "https://")
	s = strings.TrimSuffix(s, "/")

	s = strings.ReplaceAll(s, "/", "_")
	s = strings.ReplaceAll(s, ":", "_")

	s = reBad.ReplaceAllString(s, "_")
	s = strings.Trim(s, "_")

	if len(s) > 80 {
		h := sha1.Sum([]byte(u))
		s = s[:60] + "_" + hex.EncodeToString(h[:6])
	}
	if s == "" {
		h := sha1.Sum([]byte(u))
		s = hex.EncodeToString(h[:8])
	}
	return s
}
