package navigator

import (
	"regexp"
	"strings"
)

// desktopToken matches a single leading "#N" desktop prefix token, e.g. "#3" from "#3 chrome".
var desktopToken = regexp.MustCompile(`^#(\d+)(.*)`)

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

// ParseQuery splits query into (desktopNums, text).
// Leading "#N" tokens are stripped and collected into desktopNums.
// A bare "#" or whitespace-only remainder is normalised to "".
func ParseQuery(query string) (desktopNums map[int]struct{}, text string) {
	desktopNums = make(map[int]struct{})
	rest := query
	for {
		m := desktopToken.FindStringSubmatch(rest)
		if m == nil {
			break
		}
		n := 0
		for _, ch := range m[1] {
			n = n*10 + int(ch-'0')
		}
		desktopNums[n] = struct{}{}
		rest = m[2]
	}
	stripped := strings.TrimSpace(rest)
	if stripped == "#" || stripped == "" {
		return desktopNums, ""
	}
	return desktopNums, stripped
}

// FilterWindows returns windows matching query.
// Leading "#N" tokens restrict to those desktops (OR logic); remaining text is
// matched case-insensitively against title and process name.
// An empty query returns a copy of all windows.
func FilterWindows(windows []WindowInfo, query string) []WindowInfo {
	if query == "" {
		out := make([]WindowInfo, len(windows))
		copy(out, windows)
		return out
	}

	desktopNums, text := ParseQuery(query)

	if len(desktopNums) == 0 {
		if text == "" {
			out := make([]WindowInfo, len(windows))
			copy(out, windows)
			return out
		}
		var result []WindowInfo
		for _, w := range windows {
			if tokensMatch(w, text) {
				result = append(result, w)
			}
		}
		return result
	}

	var result []WindowInfo
	for _, w := range windows {
		if _, ok := desktopNums[w.DesktopNumber]; !ok {
			continue
		}
		if text == "" || tokensMatch(w, text) {
			result = append(result, w)
		}
	}
	return result
}
