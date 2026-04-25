package navigator

import "testing"

func TestDefaultTabFetcher_NotNil(t *testing.T) {
	if DefaultTabFetcher == nil {
		t.Fatal("DefaultTabFetcher must not be nil")
	}
}

func TestDefaultTabSelector_NotNil(t *testing.T) {
	if DefaultTabSelector == nil {
		t.Fatal("DefaultTabSelector must not be nil")
	}
}

func TestDefaultTabFetcher_ReturnsNilOnNonWindows(t *testing.T) {
	// On non-Windows the stub returns nil for any HWND.
	tabs := DefaultTabFetcher(0xDEAD)
	if tabs != nil {
		t.Errorf("expected nil on non-Windows, got %v", tabs)
	}
}

func TestDefaultTabSelector_NoopOnNonWindows(t *testing.T) {
	// Should not panic.
	DefaultTabSelector(TabInfo{Name: "test", HWND: 0xDEAD, Index: 0})
}

func TestTabFetcher_Injection(t *testing.T) {
	called := false
	var got uintptr
	fetcher := TabFetcher(func(hwnd uintptr) []TabInfo {
		called = true
		got = hwnd
		return []TabInfo{{Name: "Tab A", HWND: hwnd, Index: 0}}
	})

	tabs := fetcher(0x1234)
	if !called {
		t.Fatal("fetcher not called")
	}
	if got != 0x1234 {
		t.Errorf("got hwnd %#x, want %#x", got, 0x1234)
	}
	if len(tabs) != 1 || tabs[0].Name != "Tab A" {
		t.Errorf("unexpected tabs: %v", tabs)
	}
}

func TestTabSelector_Injection(t *testing.T) {
	var got TabInfo
	sel := TabSelector(func(tab TabInfo) { got = tab })
	sel(TabInfo{Name: "Tab B", HWND: 0xABCD, Index: 2})
	if got.Name != "Tab B" || got.Index != 2 {
		t.Errorf("unexpected tab: %v", got)
	}
}
