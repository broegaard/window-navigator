package navigator

import "strings"

// FilterController is the query/app-filter/bell-filter slice of the controller interface.
type FilterController interface {
	Query() string
	AppIcons() []WindowInfo
	AppFilterIndex() *int
	BellFilter() bool
	AppFilter() *string
	SetQuery(text string)
	SetDesktopNums(nums map[int]struct{})
	ToggleBellFilter()
	CycleAppFilter(direction int)
	ClearAppFilter()
}

// NavigationController is the selection/movement slice of the controller interface.
type NavigationController interface {
	SelectionIndex() int
	FlatList() []FlatItem
	FilteredWindows() []WindowInfo
	MoveUp()
	MoveDown()
	MovePageUp(pageSize int)
	MovePageDown(pageSize int)
	MoveToFirst()
	MoveToLast()
	SelectedItem() *FlatItem
	SelectedHWND() *uintptr
}

// TabController is the UIA tab discovery/expansion slice of the controller interface.
type TabController interface {
	SetTabs(hwnd uintptr, tabs []TabInfo)
	ToggleAllExpansions()
	TabCount(hwnd uintptr) int
	IsExpanded(hwnd uintptr) bool
}

// OverlayController is the full controller interface consumed by the overlay.
type OverlayController interface {
	FilterController
	NavigationController
	TabController
	Reset(windows []WindowInfo)
}

// FlatItem is a union of WindowInfo and TabInfo for the flat rendered list.
// Exactly one of Window/Tab is non-nil.
type FlatItem struct {
	Window *WindowInfo
	Tab    *TabInfo
}

// HWND returns the hwnd: the window's own hwnd, or the tab's parent hwnd.
func (f FlatItem) HWND() uintptr {
	if f.Window != nil {
		return f.Window.HWND
	}
	return f.Tab.HWND
}

// Controller implements OverlayController — pure Go, no UI dependency.
type Controller struct {
	AllWindows     []WindowInfo
	query          string
	desktopNums    map[int]struct{}
	appFilter      *string
	bellFilter     bool
	tabs           map[uintptr][]TabInfo
	expanded       map[uintptr]struct{}
	wantAllExpand  bool
	selectionIndex int
}

// NewController creates a fresh Controller for the given window list.
func NewController(windows []WindowInfo) *Controller {
	sel := -1
	if len(windows) > 0 {
		sel = 0
	}
	return &Controller{
		AllWindows:     append([]WindowInfo(nil), windows...),
		desktopNums:    make(map[int]struct{}),
		tabs:           make(map[uintptr][]TabInfo),
		expanded:       make(map[uintptr]struct{}),
		selectionIndex: sel,
	}
}

// ---------------------------------------------------------------------------
// FilterController
// ---------------------------------------------------------------------------

func (c *Controller) Query() string { return c.query }

func (c *Controller) BellFilter() bool { return c.bellFilter }

func (c *Controller) AppFilter() *string { return c.appFilter }

// AppIcons returns one representative WindowInfo per unique ProcessName in
// TextFilteredWindows, preserving recency (z-order) of first occurrence.
func (c *Controller) AppIcons() []WindowInfo {
	seen := make(map[string]struct{})
	var result []WindowInfo
	for _, w := range c.TextFilteredWindows() {
		if _, ok := seen[w.ProcessName]; !ok {
			seen[w.ProcessName] = struct{}{}
			result = append(result, w)
		}
	}
	return result
}

// AppFilterIndex returns a pointer to the index of the active app filter in AppIcons,
// or nil if no filter is active.
func (c *Controller) AppFilterIndex() *int {
	if c.appFilter == nil {
		return nil
	}
	for i, w := range c.AppIcons() {
		if w.ProcessName == *c.appFilter {
			return &i
		}
	}
	return nil
}

func (c *Controller) SetQuery(text string) {
	c.query = text
	if c.appFilter != nil {
		names := make(map[string]struct{})
		for _, w := range c.TextFilteredWindows() {
			names[w.ProcessName] = struct{}{}
		}
		hwndToWindow := make(map[uintptr]WindowInfo)
		for _, w := range c.AllWindows {
			hwndToWindow[w.HWND] = w
		}
		for h := range c.tabQueryMatches() {
			if w, ok := hwndToWindow[h]; ok {
				names[w.ProcessName] = struct{}{}
			}
		}
		if _, ok := names[*c.appFilter]; !ok {
			c.appFilter = nil
		}
	}
	flat := c.FlatList()
	if len(flat) > 0 {
		c.selectionIndex = 0
	} else {
		c.selectionIndex = -1
	}
}

func (c *Controller) SetDesktopNums(nums map[int]struct{}) {
	c.desktopNums = nums
	if c.appFilter != nil {
		names := make(map[string]struct{})
		for _, w := range c.TextFilteredWindows() {
			names[w.ProcessName] = struct{}{}
		}
		hwndToWindow := make(map[uintptr]WindowInfo)
		for _, w := range c.AllWindows {
			hwndToWindow[w.HWND] = w
		}
		for h := range c.tabQueryMatches() {
			if w, ok := hwndToWindow[h]; ok {
				names[w.ProcessName] = struct{}{}
			}
		}
		if _, ok := names[*c.appFilter]; !ok {
			c.appFilter = nil
		}
	}
	c.resetSelection()
}

func (c *Controller) ToggleBellFilter() {
	c.bellFilter = !c.bellFilter
	c.resetSelection()
}

func (c *Controller) CycleAppFilter(direction int) {
	icons := c.AppIcons()
	if len(icons) == 0 {
		return
	}
	idx := c.AppFilterIndex()
	var newIdx int
	if idx == nil {
		if direction > 0 {
			newIdx = 0
		} else {
			newIdx = len(icons) - 1
		}
	} else {
		newIdx = ((*idx) + direction + len(icons)) % len(icons)
	}
	name := icons[newIdx].ProcessName
	c.appFilter = &name
	c.resetSelection()
}

func (c *Controller) ClearAppFilter() {
	c.appFilter = nil
	c.resetSelection()
}

// ---------------------------------------------------------------------------
// Derived views
// ---------------------------------------------------------------------------

// TextFilteredWindows returns windows matching desktopNums + text query only (no app filter).
func (c *Controller) TextFilteredWindows() []WindowInfo {
	return FilterWindows(c.AllWindows, c.query, c.desktopNums)
}

// tabQueryMatches returns a map of hwnd → matching tabs for windows that are
// expanded but not matched by title/process name, when the query has text.
// Returns empty map when nothing is expanded.
func (c *Controller) tabQueryMatches() map[uintptr][]TabInfo {
	result := make(map[uintptr][]TabInfo)
	if len(c.expanded) == 0 {
		return result
	}
	if strings.TrimSpace(c.query) == "" {
		return result
	}
	tokens := strings.Fields(strings.ToLower(c.query))
	titleHWNDs := make(map[uintptr]struct{})
	for _, w := range c.TextFilteredWindows() {
		titleHWNDs[w.HWND] = struct{}{}
	}
	hwndToWindow := make(map[uintptr]WindowInfo)
	for _, w := range c.AllWindows {
		hwndToWindow[w.HWND] = w
	}
	for hwnd, tabs := range c.tabs {
		if _, ok := titleHWNDs[hwnd]; ok {
			continue
		}
		w, ok := hwndToWindow[hwnd]
		if !ok {
			continue
		}
		if len(c.desktopNums) > 0 {
			if _, ok := c.desktopNums[w.DesktopNumber]; !ok {
				continue
			}
		}
		var matching []TabInfo
		for _, t := range tabs {
			name := strings.ToLower(t.Name)
			allMatch := true
			for _, tok := range tokens {
				if !strings.Contains(name, tok) {
					allMatch = false
					break
				}
			}
			if allMatch {
				matching = append(matching, t)
			}
		}
		if len(matching) > 0 {
			result[hwnd] = matching
		}
	}
	return result
}

// FilteredWindows returns windows matching query AND all active filters.
func (c *Controller) FilteredWindows() []WindowInfo {
	titleHWNDs := make(map[uintptr]struct{})
	for _, w := range c.TextFilteredWindows() {
		titleHWNDs[w.HWND] = struct{}{}
	}
	tabMatches := c.tabQueryMatches()
	var result []WindowInfo
	for _, w := range c.AllWindows {
		_, inTitle := titleHWNDs[w.HWND]
		_, inTab := tabMatches[w.HWND]
		if !inTitle && !inTab {
			continue
		}
		if c.bellFilter && !w.HasNotification {
			continue
		}
		if c.appFilter != nil && w.ProcessName != *c.appFilter {
			continue
		}
		result = append(result, w)
	}
	return result
}

// FlatList returns filtered windows with expanded tab rows interleaved after their parent.
func (c *Controller) FlatList() []FlatItem {
	tabMatches := c.tabQueryMatches()
	var result []FlatItem
	for _, w := range c.FilteredWindows() {
		wCopy := w
		result = append(result, FlatItem{Window: &wCopy})
		if tabs, ok := tabMatches[w.HWND]; ok {
			for _, t := range tabs {
				tCopy := t
				result = append(result, FlatItem{Tab: &tCopy})
			}
		} else if _, expanded := c.expanded[w.HWND]; expanded {
			if tabs, ok := c.tabs[w.HWND]; ok {
				for _, t := range tabs {
					tCopy := t
					result = append(result, FlatItem{Tab: &tCopy})
				}
			}
		}
	}
	return result
}

// ---------------------------------------------------------------------------
// NavigationController
// ---------------------------------------------------------------------------

func (c *Controller) SelectionIndex() int { return c.selectionIndex }

func (c *Controller) MoveUp() {
	if c.selectionIndex > 0 {
		c.selectionIndex--
	}
}

func (c *Controller) MoveDown() {
	if c.selectionIndex < len(c.FlatList())-1 {
		c.selectionIndex++
	}
}

func (c *Controller) MovePageUp(pageSize int) {
	if c.selectionIndex > 0 {
		c.selectionIndex = max(0, c.selectionIndex-pageSize)
	}
}

func (c *Controller) MovePageDown(pageSize int) {
	last := len(c.FlatList()) - 1
	if c.selectionIndex < last {
		c.selectionIndex = min(last, c.selectionIndex+pageSize)
	}
}

func (c *Controller) MoveToFirst() {
	if len(c.FlatList()) > 0 {
		c.selectionIndex = 0
	}
}

func (c *Controller) MoveToLast() {
	last := len(c.FlatList()) - 1
	if last >= 0 {
		c.selectionIndex = last
	}
}

func (c *Controller) SelectedItem() *FlatItem {
	flat := c.FlatList()
	if c.selectionIndex < 0 || c.selectionIndex >= len(flat) {
		return nil
	}
	item := flat[c.selectionIndex]
	return &item
}

func (c *Controller) SelectedHWND() *uintptr {
	item := c.SelectedItem()
	if item == nil {
		return nil
	}
	h := item.HWND()
	return &h
}

// ---------------------------------------------------------------------------
// TabController
// ---------------------------------------------------------------------------

func (c *Controller) TabCount(hwnd uintptr) int {
	return len(c.tabs[hwnd])
}

func (c *Controller) IsExpanded(hwnd uintptr) bool {
	_, ok := c.expanded[hwnd]
	return ok
}

func (c *Controller) SetTabs(hwnd uintptr, tabs []TabInfo) {
	c.tabs[hwnd] = tabs
	if c.wantAllExpand && len(tabs) > 1 {
		c.expanded[hwnd] = struct{}{}
	}
}

// ToggleExpansion expands or collapses the tab list for hwnd.
// Only expands when the window has more than one tab.
// Always leaves selection on the parent window row.
func (c *Controller) ToggleExpansion(hwnd uintptr) {
	if _, ok := c.expanded[hwnd]; ok {
		delete(c.expanded, hwnd)
	} else if tabs, ok := c.tabs[hwnd]; ok && len(tabs) > 1 {
		c.expanded[hwnd] = struct{}{}
	}
	for i, item := range c.FlatList() {
		if item.Window != nil && item.Window.HWND == hwnd {
			c.selectionIndex = i
			break
		}
	}
}

func (c *Controller) ToggleAllExpansions() {
	hwndsWithTabs := make(map[uintptr]struct{})
	for _, w := range c.FilteredWindows() {
		if tabs, ok := c.tabs[w.HWND]; ok && len(tabs) > 1 {
			hwndsWithTabs[w.HWND] = struct{}{}
		}
	}
	if len(hwndsWithTabs) == 0 {
		c.wantAllExpand = !c.wantAllExpand
		return
	}
	// Check if any in hwndsWithTabs are currently expanded
	anyExpanded := false
	for hwnd := range hwndsWithTabs {
		if _, ok := c.expanded[hwnd]; ok {
			anyExpanded = true
			break
		}
	}
	if anyExpanded {
		for hwnd := range hwndsWithTabs {
			delete(c.expanded, hwnd)
		}
		c.wantAllExpand = false
	} else {
		for hwnd := range hwndsWithTabs {
			c.expanded[hwnd] = struct{}{}
		}
		c.wantAllExpand = true
	}
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

func (c *Controller) Reset(windows []WindowInfo) {
	c.AllWindows = append([]WindowInfo(nil), windows...)
	c.query = ""
	c.desktopNums = make(map[int]struct{})
	c.appFilter = nil
	c.bellFilter = false
	c.tabs = make(map[uintptr][]TabInfo)
	c.expanded = make(map[uintptr]struct{})
	c.wantAllExpand = false
	if len(windows) > 0 {
		c.selectionIndex = 0
	} else {
		c.selectionIndex = -1
	}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func (c *Controller) resetSelection() {
	flat := c.FlatList()
	if len(flat) > 0 {
		c.selectionIndex = 0
	} else {
		c.selectionIndex = -1
	}
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
