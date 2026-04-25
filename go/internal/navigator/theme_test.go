package navigator

import (
	"fmt"
	"strings"
	"testing"
)

func TestDesktopBadgeColorFormat(t *testing.T) {
	for n := 1; n <= len(DesktopColors)*2; n++ {
		got := DesktopBadgeColor(n)
		if !strings.HasPrefix(got, "#") || len(got) != 7 {
			t.Errorf("DesktopBadgeColor(%d) = %q, want 7-char hex like #rrggbb", n, got)
		}
	}
}

func TestDesktopBadgeColorMatchesPalette(t *testing.T) {
	for i, c := range DesktopColors {
		n := i + 1
		want := fmt.Sprintf("#%02x%02x%02x", c[0], c[1], c[2])
		got := DesktopBadgeColor(n)
		if got != want {
			t.Errorf("DesktopBadgeColor(%d) = %q, want %q", n, got, want)
		}
	}
}

func TestDesktopBadgeColorCycles(t *testing.T) {
	n := len(DesktopColors)
	if DesktopBadgeColor(1) != DesktopBadgeColor(n+1) {
		t.Errorf("DesktopBadgeColor(1) != DesktopBadgeColor(%d): cycling broken", n+1)
	}
}
