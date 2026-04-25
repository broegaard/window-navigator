package navigator

import "testing"

func TestFallbackIconSize(t *testing.T) {
	img := FallbackIcon()
	if img == nil {
		t.Fatal("FallbackIcon returned nil")
	}
	b := img.Bounds()
	if b.Dx() != IconSize || b.Dy() != IconSize {
		t.Errorf("expected %dx%d, got %dx%d", IconSize, IconSize, b.Dx(), b.Dy())
	}
}

func TestFallbackIconIsGrey(t *testing.T) {
	img := FallbackIcon()
	// Check top-left pixel is grey (128,128,128,255)
	r, g, b, a := img.At(0, 0).RGBA()
	// RGBA() returns 16-bit values; 128<<8|128 = 32896 ≈ 32768 (rounding)
	// Just check they're all roughly equal and non-zero
	if r == 0 || g == 0 || b == 0 || a == 0 {
		t.Errorf("fallback icon should be non-transparent grey, got r=%d g=%d b=%d a=%d", r, g, b, a)
	}
	if r != g || g != b {
		t.Errorf("fallback icon should be grey (equal RGB), got r=%d g=%d b=%d", r, g, b)
	}
}
