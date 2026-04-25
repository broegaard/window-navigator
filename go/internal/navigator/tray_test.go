package navigator

import (
	"image/color"
	"testing"
)

func TestMakeTrayIcon_Size(t *testing.T) {
	img := MakeTrayIcon(1)
	b := img.Bounds()
	if b.Dx() != TrayIconSize || b.Dy() != TrayIconSize {
		t.Fatalf("want %d×%d, got %d×%d", TrayIconSize, TrayIconSize, b.Dx(), b.Dy())
	}
}

func TestMakeTrayIcon_DesktopColor(t *testing.T) {
	for i, dc := range DesktopColors {
		n := i + 1
		img := MakeTrayIcon(n)
		got := img.RGBAAt(0, 0)
		want := color.RGBA{R: dc[0], G: dc[1], B: dc[2], A: 255}
		if got != want {
			t.Errorf("desktop %d: got %v, want %v", n, got, want)
		}
	}
}

func TestMakeTrayIcon_Unknown_Grey(t *testing.T) {
	img := MakeTrayIcon(0)
	got := img.RGBAAt(0, 0)
	want := color.RGBA{R: 60, G: 60, B: 60, A: 255}
	if got != want {
		t.Errorf("desktop 0 (unknown): got %v, want %v", got, want)
	}
}

func TestMakeTrayIcon_Cycling(t *testing.T) {
	n := len(DesktopColors)
	img1 := MakeTrayIcon(1)
	imgN1 := MakeTrayIcon(n + 1)
	if img1.RGBAAt(0, 0) != imgN1.RGBAAt(0, 0) {
		t.Errorf("desktop %d should cycle to same color as desktop 1", n+1)
	}
}

func TestMakeTrayIcon_AllPixelsOpaque(t *testing.T) {
	img := MakeTrayIcon(3)
	for y := 0; y < TrayIconSize; y++ {
		for x := 0; x < TrayIconSize; x++ {
			if a := img.RGBAAt(x, y).A; a != 255 {
				t.Fatalf("pixel (%d,%d) has alpha %d, want 255", x, y, a)
			}
		}
	}
}

func TestNewTrayIcon_NoopOnNonWindows(t *testing.T) {
	var called bool
	icon := NewTrayIcon(func() { called = true })
	icon.Start(1)
	icon.Update(2)
	icon.Stop()
	if called {
		t.Error("onExit should not have been called")
	}
}
