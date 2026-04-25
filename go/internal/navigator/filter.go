package navigator

import "strings"

// tokensMatch returns true if every whitespace-separated token in query appears
// (case-insensitively) in w's title or process name.
func tokensMatch(w WindowInfo, query string) bool {
	title := strings.ToLower(w.Title)
	proc := strings.ToLower(w.ProcessName)
	for _, tok := range strings.Fields(strings.ToLower(query)) {
		if !strings.Contains(title, tok) && !strings.Contains(proc, tok) {
			return false
		}
	}
	return true
}

// FilterWindows returns windows matching query and desktopNums.
// desktopNums restricts to those desktops (OR logic); nil means no desktop filter.
// query is matched case-insensitively against title and process name (multi-token AND).
// An empty query with nil desktopNums returns a copy of all windows.
func FilterWindows(windows []WindowInfo, query string, desktopNums map[int]struct{}) []WindowInfo {
	hasDesktopFilter := len(desktopNums) > 0
	hasTextFilter := len(strings.Fields(query)) > 0

	if !hasDesktopFilter && !hasTextFilter {
		out := make([]WindowInfo, len(windows))
		copy(out, windows)
		return out
	}

	var result []WindowInfo
	for _, w := range windows {
		if hasDesktopFilter {
			if _, ok := desktopNums[w.DesktopNumber]; !ok {
				continue
			}
		}
		if hasTextFilter && !tokensMatch(w, query) {
			continue
		}
		result = append(result, w)
	}
	return result
}
