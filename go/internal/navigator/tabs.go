package navigator

// UIA property and pattern IDs (stable across Windows versions).
const (
	UIATabItemControlType  = 50019
	UIADocumentControlType = 50030 // stop recursion here — in-page ARIA tabs live inside
	UIAControlTypeProperty = 30003
	UIANameProperty        = 30005
	UIASelectionItemPattern = 10010
	UIATreeScopeChildren   = 2
)

// TabFetcher returns the tabs for a given window HWND.
// COM must be initialised on the calling goroutine (runtime.LockOSThread + CoInitializeEx).
// Returns nil on any error or on non-Windows platforms.
type TabFetcher func(hwnd uintptr) []TabInfo

// TabSelector activates the tab described by tab on its parent window.
// COM must be initialised on the calling goroutine.
// No-ops on non-Windows or on error.
type TabSelector func(tab TabInfo)

// DefaultTabFetcher is the platform-provided TabFetcher (set by build-tag files).
var DefaultTabFetcher TabFetcher

// DefaultTabSelector is the platform-provided TabSelector (set by build-tag files).
var DefaultTabSelector TabSelector
