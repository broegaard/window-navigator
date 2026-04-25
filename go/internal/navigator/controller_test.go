package navigator

import (
	"testing"
)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func makeWindows(titles ...string) []WindowInfo {
	ws := make([]WindowInfo, len(titles))
	for i, t := range titles {
		ws[i] = WindowInfo{
			HWND:        uintptr(i + 1),
			Title:       t,
			ProcessName: "app" + string(rune('0'+i)) + ".exe",
		}
	}
	return ws
}

func makeTabs(hwnd uintptr, names ...string) []TabInfo {
	tabs := make([]TabInfo, len(names))
	for i, n := range names {
		tabs[i] = TabInfo{Name: n, HWND: hwnd, Index: i}
	}
	return tabs
}

func mixedWindows() []WindowInfo {
	return []WindowInfo{
		{HWND: 1, Title: "Notepad 1", ProcessName: "notepad.exe"},
		{HWND: 2, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 3, Title: "Notepad 2", ProcessName: "notepad.exe"},
	}
}

func desktopWindows() []WindowInfo {
	return []WindowInfo{
		{HWND: 1, Title: "Notepad", ProcessName: "notepad.exe", DesktopNumber: 1},
		{HWND: 2, Title: "Chrome", ProcessName: "chrome.exe", DesktopNumber: 2},
		{HWND: 3, Title: "Terminal", ProcessName: "wt.exe", DesktopNumber: 1},
	}
}

func notifWindows() []WindowInfo {
	return []WindowInfo{
		{HWND: 1, Title: "Slack", ProcessName: "slack.exe", HasNotification: true},
		{HWND: 2, Title: "Chrome", ProcessName: "chrome.exe", HasNotification: false},
		{HWND: 3, Title: "Teams", ProcessName: "teams.exe", HasNotification: true},
	}
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

func TestInitialSelectionIsZero(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestInitialSelectionEmptyIsMinusOne(t *testing.T) {
	c := NewController(nil)
	if c.SelectionIndex() != -1 {
		t.Errorf("expected -1, got %d", c.SelectionIndex())
	}
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

func TestMoveDownIncrements(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.MoveDown()
	if c.SelectionIndex() != 1 {
		t.Errorf("expected 1, got %d", c.SelectionIndex())
	}
}

func TestMoveUpDecrements(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.selectionIndex = 2
	c.MoveUp()
	if c.SelectionIndex() != 1 {
		t.Errorf("expected 1, got %d", c.SelectionIndex())
	}
}

func TestMoveUpClampedAtZero(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.MoveUp()
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestMoveDownClampedAtLast(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.MoveDown()
	c.MoveDown()
	c.MoveDown()
	if c.SelectionIndex() != 1 {
		t.Errorf("expected 1, got %d", c.SelectionIndex())
	}
}

func TestNavigationOnEmptyIsSafe(t *testing.T) {
	c := NewController(nil)
	c.MoveUp()
	c.MoveDown()
	if c.SelectionIndex() != -1 {
		t.Errorf("expected -1, got %d", c.SelectionIndex())
	}
}

func TestPageDownJumpsByPageSize(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"))
	c.MovePageDown(5)
	if c.SelectionIndex() != 5 {
		t.Errorf("expected 5, got %d", c.SelectionIndex())
	}
}

func TestPageDownClampedAtLast(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C", "D", "E"))
	c.selectionIndex = 3
	c.MovePageDown(10)
	if c.SelectionIndex() != 4 {
		t.Errorf("expected 4, got %d", c.SelectionIndex())
	}
}

func TestPageUpJumpsByPageSize(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"))
	c.selectionIndex = 7
	c.MovePageUp(5)
	if c.SelectionIndex() != 2 {
		t.Errorf("expected 2, got %d", c.SelectionIndex())
	}
}

func TestPageUpClampedAtZero(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C", "D", "E"))
	c.selectionIndex = 2
	c.MovePageUp(10)
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestMoveToLast(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.MoveToLast()
	if c.SelectionIndex() != 2 {
		t.Errorf("expected 2, got %d", c.SelectionIndex())
	}
}

func TestMoveToFirst(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.selectionIndex = 2
	c.MoveToFirst()
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestPageAndBoundaryOnEmptyIsSafe(t *testing.T) {
	c := NewController(nil)
	c.MovePageUp(5)
	c.MovePageDown(5)
	c.MoveToFirst()
	c.MoveToLast()
	if c.SelectionIndex() != -1 {
		t.Errorf("expected -1, got %d", c.SelectionIndex())
	}
}

// ---------------------------------------------------------------------------
// SelectedHWND
// ---------------------------------------------------------------------------

func TestSelectedHWNDReturnsCorrect(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.selectionIndex = 2
	h := c.SelectedHWND()
	if h == nil || *h != 3 {
		t.Errorf("expected hwnd 3, got %v", h)
	}
}

func TestSelectedHWNDOnEmptyIsNil(t *testing.T) {
	c := NewController(nil)
	if c.SelectedHWND() != nil {
		t.Error("expected nil")
	}
}

func TestSelectedHWNDNoMatchIsNil(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.SetQuery("zzz")
	if c.SelectedHWND() != nil {
		t.Error("expected nil")
	}
}

// ---------------------------------------------------------------------------
// Filtering
// ---------------------------------------------------------------------------

func TestSetQueryFiltersResults(t *testing.T) {
	c := NewController(makeWindows("Notepad", "Chrome", "Explorer"))
	c.SetQuery("note")
	fw := c.FilteredWindows()
	if len(fw) != 1 || fw[0].Title != "Notepad" {
		t.Errorf("unexpected: %v", fw)
	}
}

func TestSetQueryResetsSelectionToZero(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.selectionIndex = 2
	c.SetQuery("A")
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestSetQueryNoMatchGivesMinusOne(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.SetQuery("zzz")
	if c.SelectionIndex() != -1 {
		t.Errorf("expected -1, got %d", c.SelectionIndex())
	}
}

func TestSetQueryEmptyRestoresAll(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.SetQuery("A")
	c.SetQuery("")
	if len(c.FilteredWindows()) != 3 {
		t.Errorf("expected 3, got %d", len(c.FilteredWindows()))
	}
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

func TestResetClearsQueryAndSelection(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.SetQuery("A")
	c.Reset(makeWindows("X", "Y", "Z"))
	if c.Query() != "" || len(c.FilteredWindows()) != 3 || c.SelectionIndex() != 0 {
		t.Errorf("unexpected state after reset")
	}
}

func TestResetToEmptyList(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.Reset(nil)
	if c.SelectionIndex() != -1 || c.SelectedHWND() != nil {
		t.Errorf("unexpected state")
	}
}

func TestSetQueryDoesNotMutateAllWindows(t *testing.T) {
	c := NewController(makeWindows("A", "B", "C"))
	c.SetQuery("A")
	if len(c.AllWindows) != 3 {
		t.Errorf("AllWindows mutated: %d", len(c.AllWindows))
	}
}

func TestResetReplacesAllWindows(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.Reset(makeWindows("X", "Y", "Z"))
	if len(c.AllWindows) != 3 || c.AllWindows[0].Title != "X" {
		t.Errorf("unexpected AllWindows: %v", c.AllWindows)
	}
}

// ---------------------------------------------------------------------------
// Desktop prefix in controller
// ---------------------------------------------------------------------------

func TestControllerDesktopPrefixFilters(t *testing.T) {
	c := NewController(desktopWindows())
	c.SetQuery("#1")
	fw := c.FilteredWindows()
	if len(fw) != 2 {
		t.Errorf("expected 2, got %d", len(fw))
	}
	for _, w := range fw {
		if w.DesktopNumber != 1 {
			t.Errorf("unexpected desktop %d", w.DesktopNumber)
		}
	}
}

func TestControllerDesktopPrefixWithText(t *testing.T) {
	c := NewController(desktopWindows())
	c.SetQuery("#1 note")
	fw := c.FilteredWindows()
	if len(fw) != 1 || fw[0].Title != "Notepad" {
		t.Errorf("unexpected: %v", fw)
	}
}

// ---------------------------------------------------------------------------
// AppIcons
// ---------------------------------------------------------------------------

func TestAppIconsDeduplicatedByProcessName(t *testing.T) {
	c := NewController(mixedWindows())
	icons := c.AppIcons()
	if len(icons) != 2 {
		t.Errorf("expected 2, got %d", len(icons))
	}
	if icons[0].ProcessName != "notepad.exe" || icons[1].ProcessName != "chrome.exe" {
		t.Errorf("unexpected icons: %v", icons)
	}
}

func TestAppIconsFirstOccurrenceChosen(t *testing.T) {
	c := NewController(mixedWindows())
	icons := c.AppIcons()
	if icons[0].HWND != 1 {
		t.Errorf("expected hwnd 1, got %d", icons[0].HWND)
	}
}

func TestAppIconsRespectsTextFilter(t *testing.T) {
	c := NewController(mixedWindows())
	c.SetQuery("notepad")
	icons := c.AppIcons()
	if len(icons) != 1 || icons[0].ProcessName != "notepad.exe" {
		t.Errorf("unexpected: %v", icons)
	}
}

func TestAppIconsEmptyWhenNoTextMatch(t *testing.T) {
	c := NewController(mixedWindows())
	c.SetQuery("zzz")
	if len(c.AppIcons()) != 0 {
		t.Error("expected empty")
	}
}

// ---------------------------------------------------------------------------
// CycleAppFilter
// ---------------------------------------------------------------------------

func TestCycleAppFilterForwardStartsAtZero(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1)
	if idx := c.AppFilterIndex(); idx == nil || *idx != 0 {
		t.Errorf("expected index 0")
	}
	if c.AppFilter() == nil || *c.AppFilter() != "notepad.exe" {
		t.Errorf("expected notepad.exe")
	}
}

func TestCycleAppFilterBackwardStartsAtLast(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(-1)
	if idx := c.AppFilterIndex(); idx == nil || *idx != 1 {
		t.Errorf("expected index 1")
	}
}

func TestCycleAppFilterWrapsForward(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1) // notepad
	c.CycleAppFilter(1) // chrome
	c.CycleAppFilter(1) // wraps → notepad
	if c.AppFilter() == nil || *c.AppFilter() != "notepad.exe" {
		t.Errorf("expected notepad.exe after wrap")
	}
}

func TestCycleAppFilterWrapsBackward(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1)  // notepad
	c.CycleAppFilter(-1) // wraps → chrome
	if c.AppFilter() == nil || *c.AppFilter() != "chrome.exe" {
		t.Errorf("expected chrome.exe after wrap")
	}
}

func TestCycleAppFilterResetsSelection(t *testing.T) {
	c := NewController(mixedWindows())
	c.selectionIndex = 2
	c.CycleAppFilter(1)
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

func TestCycleAppFilterNoopOnEmpty(t *testing.T) {
	c := NewController(nil)
	c.CycleAppFilter(1)
	if c.AppFilter() != nil {
		t.Error("expected nil filter")
	}
}

// ---------------------------------------------------------------------------
// ClearAppFilter
// ---------------------------------------------------------------------------

func TestClearAppFilterRemovesFilter(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1)
	c.ClearAppFilter()
	if c.AppFilter() != nil || c.AppFilterIndex() != nil {
		t.Error("expected nil after clear")
	}
}

func TestClearAppFilterRestoresAllWindows(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1)
	c.ClearAppFilter()
	if len(c.FilteredWindows()) != 3 {
		t.Errorf("expected 3, got %d", len(c.FilteredWindows()))
	}
}

// ---------------------------------------------------------------------------
// Auto-clear app filter when query makes it disappear
// ---------------------------------------------------------------------------

func TestSetQueryClearsAppFilterWhenAppLeaves(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1) // notepad
	c.SetQuery("chrome")
	if c.AppFilter() != nil {
		t.Errorf("expected nil, got %v", c.AppFilter())
	}
}

func TestSetQueryKeepsAppFilterWhenStillPresent(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1) // notepad
	c.SetQuery("notepad")
	if c.AppFilter() == nil || *c.AppFilter() != "notepad.exe" {
		t.Error("expected notepad.exe to survive")
	}
}

func TestResetClearsAppFilter(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1)
	c.Reset(makeWindows("X", "Y"))
	if c.AppFilter() != nil || len(c.FilteredWindows()) != 2 {
		t.Errorf("unexpected state after reset")
	}
}

func TestSetQueryEmptyKeepsAppFilterWhenAppPresent(t *testing.T) {
	c := NewController(mixedWindows())
	c.CycleAppFilter(1) // notepad
	c.SetQuery("notepad")
	c.SetQuery("") // back to all — notepad still present
	if c.AppFilter() == nil || *c.AppFilter() != "notepad.exe" {
		t.Error("app filter should persist")
	}
}

// ---------------------------------------------------------------------------
// Bell filter
// ---------------------------------------------------------------------------

func TestBellFilterIsFalseInitially(t *testing.T) {
	c := NewController(notifWindows())
	if c.BellFilter() {
		t.Error("expected false")
	}
}

func TestToggleBellFilterSetsTrue(t *testing.T) {
	c := NewController(notifWindows())
	c.ToggleBellFilter()
	if !c.BellFilter() {
		t.Error("expected true")
	}
}

func TestToggleBellFilterTogglesBack(t *testing.T) {
	c := NewController(notifWindows())
	c.ToggleBellFilter()
	c.ToggleBellFilter()
	if c.BellFilter() {
		t.Error("expected false")
	}
}

func TestBellFilterRestrictsToNotifWindows(t *testing.T) {
	c := NewController(notifWindows())
	c.ToggleBellFilter()
	fw := c.FilteredWindows()
	if len(fw) != 2 {
		t.Errorf("expected 2, got %d", len(fw))
	}
	for _, w := range fw {
		if !w.HasNotification {
			t.Errorf("non-notif window %v included", w)
		}
	}
}

func TestBellFilterEmptyWhenNoNotifications(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	c.ToggleBellFilter()
	if len(c.FilteredWindows()) != 0 || c.SelectionIndex() != -1 {
		t.Error("expected empty with -1 selection")
	}
}

func TestBellFilterClearedByReset(t *testing.T) {
	c := NewController(notifWindows())
	c.ToggleBellFilter()
	c.Reset(makeWindows("X", "Y"))
	if c.BellFilter() || len(c.FilteredWindows()) != 2 {
		t.Error("bell filter should clear on reset")
	}
}

// ---------------------------------------------------------------------------
// TabCount / IsExpanded / SetTabs
// ---------------------------------------------------------------------------

func TestTabCountZeroForUnknown(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	if c.TabCount(1) != 0 {
		t.Error("expected 0")
	}
}

func TestSetTabsStoresCount(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B", "C"))
	if c.TabCount(1) != 3 {
		t.Errorf("expected 3, got %d", c.TabCount(1))
	}
}

func TestSetTabsReplacesExisting(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(1, makeTabs(1, "Only"))
	if c.TabCount(1) != 1 {
		t.Errorf("expected 1, got %d", c.TabCount(1))
	}
}

func TestIsExpandedFalseInitially(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	if c.IsExpanded(1) {
		t.Error("expected false")
	}
}

func TestIsExpandedTrueWhenInSet(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.expanded[1] = struct{}{}
	if !c.IsExpanded(1) {
		t.Error("expected true")
	}
}

func TestResetClearsTabsAndExpanded(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.expanded[1] = struct{}{}
	c.Reset([]WindowInfo{{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"}})
	if c.TabCount(1) != 0 || c.IsExpanded(1) {
		t.Error("expected tabs and expanded cleared")
	}
}

// ---------------------------------------------------------------------------
// ToggleExpansion
// ---------------------------------------------------------------------------

func TestToggleExpansionExpandsMultiTab(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.ToggleExpansion(1)
	if !c.IsExpanded(1) {
		t.Error("expected expanded")
	}
}

func TestToggleExpansionCollapsesWhenExpanded(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.ToggleExpansion(1)
	c.ToggleExpansion(1)
	if c.IsExpanded(1) {
		t.Error("expected collapsed")
	}
}

func TestToggleExpansionDoesNotExpandSingleTab(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Only"))
	c.ToggleExpansion(1)
	if c.IsExpanded(1) {
		t.Error("single-tab window should not expand")
	}
}

func TestToggleExpansionFlatListIncludesAllTabs(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B", "C"))
	c.ToggleExpansion(1)
	flat := c.FlatList()
	if len(flat) != 4 {
		t.Errorf("expected 4, got %d", len(flat))
	}
	if flat[0].Window == nil {
		t.Error("first item should be a window")
	}
	for _, item := range flat[1:] {
		if item.Tab == nil {
			t.Error("remaining items should be tabs")
		}
	}
}

func TestToggleExpansionSetsSelectionToParent(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Firefox", ProcessName: "firefox.exe"},
		{HWND: 2, Title: "Chrome", ProcessName: "chrome.exe"},
	}
	c := NewController(windows)
	c.SetTabs(2, makeTabs(2, "A", "B"))
	c.selectionIndex = 1 // chrome
	c.ToggleExpansion(2)
	// flat: [firefox, chrome, A, B]; chrome is at index 1
	if c.SelectionIndex() != 1 {
		t.Errorf("expected 1, got %d", c.SelectionIndex())
	}
	if flat := c.FlatList(); flat[c.SelectionIndex()].Window == nil || flat[c.SelectionIndex()].Window.HWND != 2 {
		t.Error("selection should be on chrome")
	}
}

func TestToggleExpansionCollapseResetsSelectionToParent(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.ToggleExpansion(1)
	c.selectionIndex = 2 // a tab row
	c.ToggleExpansion(1) // collapse
	if c.SelectionIndex() != 0 {
		t.Errorf("expected 0, got %d", c.SelectionIndex())
	}
}

// ---------------------------------------------------------------------------
// ToggleAllExpansions
// ---------------------------------------------------------------------------

func TestToggleAllExpansionsExpandsAll(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(2, makeTabs(2, "C", "D"))
	c.ToggleAllExpansions()
	if !c.IsExpanded(1) || !c.IsExpanded(2) {
		t.Error("expected both expanded")
	}
}

func TestToggleAllExpansionsCollapsesWhenAnyExpanded(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(2, makeTabs(2, "C", "D"))
	c.expanded[1] = struct{}{}
	c.ToggleAllExpansions()
	if c.IsExpanded(1) || c.IsExpanded(2) {
		t.Error("expected both collapsed")
	}
}

func TestToggleAllExpansionsSkipsSingleTab(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(2, makeTabs(2, "Only"))
	c.ToggleAllExpansions()
	if !c.IsExpanded(1) {
		t.Error("chrome should expand")
	}
	if c.IsExpanded(2) {
		t.Error("firefox (single tab) should not expand")
	}
}

func TestToggleAllExpansionsSkipsNoTabs(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.ToggleAllExpansions()
	if c.IsExpanded(1) {
		t.Error("should not expand with no tabs")
	}
}

func TestToggleAllExpansionsRespectsActiveFilter(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(2, makeTabs(2, "C", "D"))
	c.SetQuery("chrome")
	c.ToggleAllExpansions()
	if !c.IsExpanded(1) {
		t.Error("chrome should expand")
	}
	if c.IsExpanded(2) {
		t.Error("firefox not visible — should not be touched")
	}
}

func TestToggleAllExpansionsCollapseOnlyTouchesVisible(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.SetTabs(2, makeTabs(2, "C", "D"))
	c.expanded[1] = struct{}{}
	c.expanded[2] = struct{}{}
	c.SetQuery("chrome")
	c.ToggleAllExpansions() // collapses visible chrome; firefox hidden
	if c.IsExpanded(1) {
		t.Error("chrome should collapse")
	}
	if !c.IsExpanded(2) {
		t.Error("firefox (hidden) should remain expanded")
	}
}

func TestToggleAllExpansionsDeferredExpandsWhenTabsArrive(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.ToggleAllExpansions() // no tabs yet
	if c.IsExpanded(1) {
		t.Error("should not expand yet")
	}
	c.SetTabs(1, makeTabs(1, "A", "B"))
	if !c.IsExpanded(1) {
		t.Error("should auto-expand on tab arrival")
	}
}

func TestToggleAllExpansionsDeferredSkipsSingleTab(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.ToggleAllExpansions()
	c.SetTabs(1, makeTabs(1, "Only"))
	if c.IsExpanded(1) {
		t.Error("single tab should not auto-expand")
	}
}

func TestToggleAllExpansionsDeferredCancelPreventsAutoExpand(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.ToggleAllExpansions() // set
	c.ToggleAllExpansions() // cancel
	c.SetTabs(1, makeTabs(1, "A", "B"))
	if c.IsExpanded(1) {
		t.Error("cancelled deferred should not expand")
	}
}

func TestToggleAllExpansionsCollapseClears_wantAllExpand(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "A", "B"))
	c.wantAllExpand = true
	c.expanded[1] = struct{}{}
	c.ToggleAllExpansions()
	if c.IsExpanded(1) || c.wantAllExpand {
		t.Error("expected collapsed and wantAllExpand cleared")
	}
}

func TestResetClears_wantAllExpand(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.wantAllExpand = true
	c.Reset([]WindowInfo{{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe"}})
	if c.wantAllExpand {
		t.Error("expected wantAllExpand cleared by reset")
	}
}

// ---------------------------------------------------------------------------
// SelectedItem
// ---------------------------------------------------------------------------

func TestSelectedItemNilForEmpty(t *testing.T) {
	c := NewController(nil)
	if c.SelectedItem() != nil {
		t.Error("expected nil")
	}
}

func TestSelectedItemReturnsWindowInfo(t *testing.T) {
	c := NewController(makeWindows("A", "B"))
	item := c.SelectedItem()
	if item == nil || item.Window == nil || item.Window.HWND != 1 {
		t.Error("expected window hwnd 1")
	}
}

func TestSelectedItemReturnsTabOnTabRow(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Tab A", "Tab B"))
	c.expanded[1] = struct{}{}
	c.selectionIndex = 1
	item := c.SelectedItem()
	if item == nil || item.Tab == nil || item.Tab.Name != "Tab A" {
		t.Errorf("expected Tab A, got %v", item)
	}
}

func TestSelectedItemOutOfBoundsIsNil(t *testing.T) {
	c := NewController(makeWindows("A"))
	c.selectionIndex = 99
	if c.SelectedItem() != nil {
		t.Error("expected nil")
	}
}

func TestSelectedItemNegativeIsNil(t *testing.T) {
	c := NewController(makeWindows("A"))
	c.selectionIndex = -1
	if c.SelectedItem() != nil {
		t.Error("expected nil")
	}
}

func TestSelectedHWNDOnTabRowReturnsParent(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 42, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(42, makeTabs(42, "A", "B"))
	c.expanded[42] = struct{}{}
	c.selectionIndex = 1
	h := c.SelectedHWND()
	if h == nil || *h != 42 {
		t.Errorf("expected 42, got %v", h)
	}
}

// ---------------------------------------------------------------------------
// Tab search
// ---------------------------------------------------------------------------

func TestTabSearchOffWhenCollapsed(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox", "GitHub"))
	c.SetQuery("inbox")
	if len(c.FilteredWindows()) != 0 {
		t.Error("tab search should be off when collapsed")
	}
}

func TestTabSearchOnWhenExpanded(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox", "GitHub"))
	c.expanded[1] = struct{}{}
	c.SetQuery("inbox")
	if len(c.FilteredWindows()) != 1 || c.FilteredWindows()[0].HWND != 1 {
		t.Error("tab search should surface window via tab match")
	}
}

func TestTabMatchShowsOnlyMatchingTabs(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox", "GitHub", "Gmail - Sent"))
	c.expanded[1] = struct{}{}
	c.SetQuery("gmail")
	flat := c.FlatList()
	if len(flat) != 3 {
		t.Errorf("expected 3, got %d", len(flat))
	}
}

func TestTitleMatchedWindowShowsAllTabs(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox", "GitHub", "Google"))
	c.expanded[1] = struct{}{}
	c.SetQuery("chrome")
	flat := c.FlatList()
	if len(flat) != 4 {
		t.Errorf("expected 4, got %d", len(flat))
	}
}

func TestTabSearchMultiToken(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox", "GitHub Pull Requests", "Google"))
	c.expanded[1] = struct{}{}
	c.SetQuery("github pull")
	flat := c.FlatList()
	if len(flat) != 2 || flat[1].Tab == nil || flat[1].Tab.Name != "GitHub Pull Requests" {
		t.Errorf("unexpected flat: %v", flat)
	}
}

func TestTabSearchRespectsDesktopFilter(t *testing.T) {
	windows := []WindowInfo{
		{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe", DesktopNumber: 1},
		{HWND: 2, Title: "Firefox", ProcessName: "firefox.exe", DesktopNumber: 2},
	}
	c := NewController(windows)
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox"))
	c.SetTabs(2, makeTabs(2, "Inbox - Firefox"))
	c.expanded[1] = struct{}{}
	c.expanded[2] = struct{}{}
	c.SetQuery("#1 inbox")
	fw := c.FilteredWindows()
	if len(fw) != 1 || fw[0].HWND != 1 {
		t.Errorf("expected only hwnd 1, got %v", fw)
	}
}

func TestSetQueryKeepsAppFilterWhenMatchesViaTab(t *testing.T) {
	c := NewController([]WindowInfo{{HWND: 1, Title: "Chrome", ProcessName: "chrome.exe"}})
	c.SetTabs(1, makeTabs(1, "Gmail - Inbox"))
	c.expanded[1] = struct{}{}
	c.CycleAppFilter(1) // select chrome
	c.SetQuery("inbox")
	if c.AppFilter() == nil || *c.AppFilter() != "chrome.exe" {
		t.Error("app filter should survive tab-based match")
	}
}
