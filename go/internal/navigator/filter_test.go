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
// FilterWindows — text matching
// ---------------------------------------------------------------------------

func TestEmptyQueryReturnsAll(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe"), makeWindow("Chrome", "chrome.exe")}
	got := FilterWindows(windows, "", nil)
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("expected all windows, got %v", got)
	}
}

func TestReturnsNewSlice(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe")}
	got := FilterWindows(windows, "", nil)
	if &got[0] == &windows[0] {
		t.Error("expected a copy, got same backing array")
	}
}

func TestMatchOnTitle(t *testing.T) {
	w1 := makeWindow("Notepad", "notepad.exe")
	w2 := makeWindow("Chrome", "chrome.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "note", nil)
	if len(got) != 1 || got[0].Title != "Notepad" {
		t.Errorf("unexpected result: %v", got)
	}
}

func TestMatchOnProcessName(t *testing.T) {
	w1 := makeWindow("New Tab", "chrome.exe")
	w2 := makeWindow("Editor", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "chrome", nil)
	if len(got) != 1 || got[0].ProcessName != "chrome.exe" {
		t.Errorf("unexpected result: %v", got)
	}
}

func TestCaseInsensitive(t *testing.T) {
	w := makeWindow("Notepad", "notepad.exe")
	for _, q := range []string{"NOTE", "NoteP"} {
		got := FilterWindows([]WindowInfo{w}, q, nil)
		if len(got) != 1 {
			t.Errorf("query %q: expected match", q)
		}
	}
}

func TestNoMatchReturnsEmpty(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe")}
	got := FilterWindows(windows, "zzz", nil)
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
	got := FilterWindows(windows, "app", nil)
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("order changed: %v", got)
	}
}

func TestEmptyWindowsList(t *testing.T) {
	got := FilterWindows(nil, "anything", nil)
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestMultiWordNonContiguous(t *testing.T) {
	w1 := makeWindow("aa bb cc", "app.exe")
	w2 := makeWindow("aa dd", "app.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "aa cc", nil)
	if len(got) != 1 || got[0].Title != "aa bb cc" {
		t.Errorf("unexpected: %v", got)
	}
}

func TestMultiWordAllMustMatch(t *testing.T) {
	w := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w}, "note zzz", nil)
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestMultiWordAcrossTitleAndProcess(t *testing.T) {
	w := makeWindow("Editor", "chrome.exe")
	got := FilterWindows([]WindowInfo{w}, "edit chrome", nil)
	if len(got) != 1 {
		t.Errorf("expected match, got %v", got)
	}
}

func TestWhitespaceOnlyMatchesAll(t *testing.T) {
	windows := []WindowInfo{makeWindow("Notepad", "notepad.exe"), makeWindow("Chrome", "chrome.exe")}
	got := FilterWindows(windows, "   ", nil)
	if !reflect.DeepEqual(got, windows) {
		t.Errorf("expected all windows, got %v", got)
	}
}

// ---------------------------------------------------------------------------
// FilterWindows — desktopNums parameter
// ---------------------------------------------------------------------------

func TestDesktopNumsNilReturnsAll(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2}, "", nil)
	if len(got) != 2 {
		t.Errorf("expected 2, got %v", got)
	}
}

func TestDesktopNumsSingleFilter(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	w3 := makeDesktopWindow("Terminal", "wt.exe", 1)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "", map[int]struct{}{1: {}})
	if len(got) != 2 {
		t.Errorf("expected 2, got %v", got)
	}
	for _, w := range got {
		if w.DesktopNumber != 1 {
			t.Errorf("unexpected desktop %d", w.DesktopNumber)
		}
	}
}

func TestDesktopNumsOrSemantics(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Chrome", "chrome.exe", 2)
	w3 := makeDesktopWindow("Terminal", "wt.exe", 3)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "", map[int]struct{}{1: {}, 2: {}})
	if len(got) != 2 {
		t.Errorf("expected 2, got %v", got)
	}
}

func TestDesktopNumsCombinedWithText(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	w2 := makeDesktopWindow("Terminal", "wt.exe", 1)
	w3 := makeDesktopWindow("Notepad", "notepad.exe", 2)
	got := FilterWindows([]WindowInfo{w1, w2, w3}, "note", map[int]struct{}{1: {}})
	if len(got) != 1 || got[0].Title != "Notepad" || got[0].DesktopNumber != 1 {
		t.Errorf("unexpected: %v", got)
	}
}

func TestDesktopNumsUnknownExcluded(t *testing.T) {
	w1 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	got := FilterWindows([]WindowInfo{w1}, "", map[int]struct{}{99: {}})
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestDesktopNumsZeroIsValid(t *testing.T) {
	w1 := makeDesktopWindow("Unknown", "app.exe", 0)
	w2 := makeDesktopWindow("Notepad", "notepad.exe", 1)
	got := FilterWindows([]WindowInfo{w1, w2}, "", map[int]struct{}{0: {}})
	if len(got) != 1 || got[0].DesktopNumber != 0 {
		t.Errorf("unexpected: %v", got)
	}
}

// ---------------------------------------------------------------------------
// FilterWindows — # and #N as plain text
// ---------------------------------------------------------------------------

func TestHashIsPlainText(t *testing.T) {
	w1 := makeWindow("#tag", "app.exe")
	w2 := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "#", nil)
	if len(got) != 1 || got[0].Title != "#tag" {
		t.Errorf("# should be plain text matching only #tag, got %v", got)
	}
}

func TestHashNIsPlainText(t *testing.T) {
	w1 := makeWindow("#1 result", "app.exe")
	w2 := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "#1", nil)
	if len(got) != 1 || got[0].Title != "#1 result" {
		t.Errorf("#1 should be plain text, got %v", got)
	}
}

func TestHashNonDigitIsTextFilter(t *testing.T) {
	w1 := makeWindow("#abc window", "app.exe")
	w2 := makeWindow("Notepad", "notepad.exe")
	got := FilterWindows([]WindowInfo{w1, w2}, "#abc", nil)
	if len(got) != 1 || got[0].Title != "#abc window" {
		t.Errorf("unexpected: %v", got)
	}
}
