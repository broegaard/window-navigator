package navigator

import (
	"reflect"
	"testing"
)

func makeWindow(title, processName string) WindowInfo {
	return WindowInfo{HWND: 1, Title: title, ProcessName: processName}
}

func makeDesktopWindow(title, processName string, desktop int) WindowInfo {
	return WindowInfo{HWND: 1, Title: title, ProcessName: processName, DesktopNumber: desktop}
}

// ---------------------------------------------------------------------------
// FilterWindows
// ---------------------------------------------------------------------------

func TestEmptyQueryReturnsAll(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe"), makeWindow("Chrome", "chrome.exe")}
	got := FilterWindows(windows, "")
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("expected all windows, got %v", got)
	}
}

func TestReturnsNewSlice(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe")}
	got := FilterWindows(windows, "")
	if &got[0] == &windows[0] {
		t.Error("expected a copy, got same backing array")
	}
}

func TestMatchOnTitle(t *testing.T) {
	w1 := makeWindow("Notepad", "notepad.exe")
	w2 := makeWindow("Chrome", "chrome.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "note")
	if len(got) != 1 || got[0].Title != "Notepad" {
		t.Errorf("unexpected result: %v", got)
	}
}

func TestMatchOnProcessName(t *testing.T) {
	w1 := makeWindow("New Tab", "chrome.exe")
	w2 := makeWindow("Editor", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "chrome")
	if len(got) != 1 || got[0].ProcessName != "chrome.exe" {
		t.Errorf("unexpected result: %v", got)
	}
}

func TestCaseInsensitive(t *testing.T) {
	w := makeWindow("Notepad", "notepad.exe")
	for _, q := range []string{"NOTE", "NoteP"} {
		got := FilterWindows([]WindowInfo{w}, q)
		if len(got) != 1 {
			t.Errorf("query %q: expected match", q)
		}
	}
}

func TestNoMatchReturnsEmpty(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe")}
	got := FilterWindows(windows, "zzz")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestPreservesOrder(t *testing.T) {
	windows := []WindowInfo{
		makeWindow("Alpha App", "alpha.exe"),
		makeWindow("Beta App", "beta.exe"),
		makeWindow("Gamma App", "gamma.exe"),
	}
	got := FilterWindows(windows, "app")
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("order changed: %v", got)
	}
}

func TestEmptyWindowsList(t *testing.T) {
	got := FilterWindows(nil, "anything")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestMultiWordNonContiguous(t *testing.T) {
	w1 := makeWindow("aa bb cc", "app.exe")
	w2 := makeWindow("aa dd", "app.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "aa cc")
	if len(got) != 1 || got[0].Title != "aa bb cc" {
		t.Errorf("unexpected: %v", got)
	}
}

func TestMultiWordAllMustMatch(t *testing.T) {
	w := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w}, "note zzz")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestMultiWordAcrossTitleAndProcess(t *testing.T) {
	w := makeWindow("Editor", "chrome.exe")
	got := FilterWindows([]WindowInfo{w}, "edit chrome")
	if len(got) != 1 {
		t.Errorf("expected match, got %v", got)
	}
}

func TestWhitespaceOnlyMatchesAll(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe"), makeWindow("Chrome", "chrome.exe")}
	got := FilterWindows(windows, "   ")
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("expected all windows, got %v", got)
	}
}

// ---------------------------------------------------------------------------
// Desktop prefix
// ---------------------------------------------------------------------------

func TestDesktopPrefixFiltersByDesktop(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	w3 := makeDesktopWindow("Terminal", "wt.exe", 1)
	got1 := FilterWindows([]WindowInfo{w1, w2, w3}, "#1")
	if len(got1) != 2 {
		t.Errorf("#1: expected 2, got %v", got1)
	}
	got2 := FilterWindows([]WindowInfo{w1, w2, w3}, "#2")
	if len(got2) != 1 || got2[0].ProcessName != "chrome.exe" {
		t.Errorf("#2: unexpected %v", got2)
	}
}

func TestDesktopPrefixWithText(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Terminal", "wt.exe", 1)
	w3 := makeDesktopWindow("Notepad", "notepad.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "#1 note")
	if len(got) != 1 || got[0].Title != "Notepad" || got[0].DesktopNumber != 1 {
		t.Errorf("unexpected: %v", got)
	}
}

func TestDesktopPrefixNoMatchReturnsEmpty(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	got := FilterWindows([]WindowInfo{w1}, "#99")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestDesktopPrefixUnknownDesktopExcluded(t *testing.T) {
	w := makeDesktopWindow("Notepad", "notepad.exe", 0)
	got := FilterWindows([]WindowInfo{w}, "#1")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestHashAloneReturnsAll(t *testing.T) {
	w1 := makeWindow("#tag", "app.exe")
	w2 := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "#")
	if len(got) != 2 {
		t.Errorf("expected 2, got %v", got)
	}
}

func TestHashNonDigitIsTextFilter(t *testing.T) {
	w1 := makeWindow("#abc window", "app.exe")
	w2 := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "#abc")
	if len(got) != 1 || got[0].Title != "#abc window" {
		t.Errorf("unexpected: %v", got)
	}
}

func TestDesktopPrefixMultiDigit(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 10)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 1)
	got := FilterWindows([]WindowInfo{w1, w2}, "#10")
	if len(got) != 1 || got[0].DesktopNumber != 10 {
		t.Errorf("unexpected: %v", got)
	}
}

func TestDesktopPrefixTrailingSpace(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 3)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2}, "#3 ")
	if len(got) != 1 || got[0].DesktopNumber != 3 {
		t.Errorf("unexpected: %v", got)
	}
}

func TestMultiDesktopPrefixOrSemantics(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	w3 := makeDesktopWindow("Terminal", "wt.exe", 3)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "#1#2")
	if len(got) != 2 {
		t.Errorf("expected 2, got %v", got)
	}
}

func TestMultiDesktopPrefixWithText(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	w3 := makeDesktopWindow("Firefox", "firefox.exe", 1)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "#1#2note")
	if len(got) != 1 || got[0].Title != "Notepad" {
		t.Errorf("unexpected: %v", got)
	}
}

func TestSpaceBreaksMultiDesktopPrefixChain(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2}, "#1 #2")
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestTrailingHashAfterDesktopPrefixIgnored(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2}, "#1#")
	if len(got) != 1 || got[0].DesktopNumber != 1 {
		t.Errorf("unexpected: %v", got)
	}
}

func TestDesktopPrefixZeroIsValid(t *testing.T) {
	w1 := makeDesktopWindow("Unknown", "app.exe", 0)
	w2 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	got := FilterWindows([]WindowInfo{w1, w2}, "#0")
	if len(got) != 1 || got[0].DesktopNumber != 0 {
		t.Errorf("unexpected: %v", got)
	}
}

// ---------------------------------------------------------------------------
// ParseQuery
// ---------------------------------------------------------------------------

func TestParseQueryEmpty(t *testing.T) {
	nums, text := ParseQuery("")
	if len(nums) != 0 || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryBareHash(t *testing.T) {
	nums, text := ParseQuery("#")
	if len(nums) != 0 || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQuerySinglePrefix(t *testing.T) {
	nums, text := ParseQuery("#3")
	if _, ok := nums[3]; !ok || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryPrefixWithText(t *testing.T) {
	nums, text := ParseQuery("#3 chrome")
	if _, ok := nums[3]; !ok || text != "chrome" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryMultiPrefix(t *testing.T) {
	nums, text := ParseQuery("#1#2")
	if _, ok1 := nums[1]; !ok1 {
		t.Errorf("missing 1: %v", nums)
	}
	if _, ok2 := nums[2]; !ok2 {
		t.Errorf("missing 2: %v", nums)
	}
	if text != "" {
		t.Errorf("expected empty text, got %q", text)
	}
}

func TestParseQueryMultiDigitPrefix(t *testing.T) {
	nums, text := ParseQuery("#10")
	if _, ok := nums[10]; !ok || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryThreePrefixes(t *testing.T) {
	nums, _ := ParseQuery("#1#2#3")
	for _, n := range []int{1, 2, 3} {
		if _, ok := nums[n]; !ok {
			t.Errorf("missing %d: %v", n, nums)
		}
	}
}

func TestParseQueryPlainTextEmptySet(t *testing.T) {
	nums, text := ParseQuery("chrome")
	if len(nums) != 0 || text != "chrome" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryHashNonDigitIsPlainText(t *testing.T) {
	nums, text := ParseQuery("#abc")
	if len(nums) != 0 || text != "#abc" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryWhitespaceOnlyNormalisedToEmpty(t *testing.T) {
	nums, text := ParseQuery("   ")
	if len(nums) != 0 || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryTrailingSpaceAfterPrefix(t *testing.T) {
	nums, text := ParseQuery("#3 ")
	if _, ok := nums[3]; !ok || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryPrefixThenBareHash(t *testing.T) {
	nums, text := ParseQuery("#1#")
	if _, ok := nums[1]; !ok || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}

func TestParseQueryPrefixZero(t *testing.T) {
	nums, text := ParseQuery("#0")
	if _, ok := nums[0]; !ok || text != "" {
		t.Errorf("unexpected: %v %q", nums, text)
	}
}
