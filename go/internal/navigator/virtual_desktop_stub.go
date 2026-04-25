//go:build !windows

package navigator

import "fmt"

// nullDesktopSwitcher is a no-op DesktopSwitcher for non-Windows builds.
type nullDesktopSwitcher struct{}

func (nullDesktopSwitcher) MoveWindowToCurrent(_ uintptr) error { return fmt.Errorf("not on Windows") }
func (nullDesktopSwitcher) MoveWindowTo(_ uintptr, _ int) error { return fmt.Errorf("not on Windows") }
func (nullDesktopSwitcher) SwitchTo(_ int) error                { return fmt.Errorf("not on Windows") }

// DefaultDesktopSwitcher returns a no-op switcher on non-Windows.
func DefaultDesktopSwitcher() DesktopSwitcher { return nullDesktopSwitcher{} }

// DefaultVirtualDesktopManager returns nil on non-Windows.
func DefaultVirtualDesktopManager() VirtualDesktopManager { return nil }

// DefaultRegistryDesktopReader returns a reader that always errors on non-Windows.
func DefaultRegistryDesktopReader() RegistryDesktopReader {
	return func() ([]byte, []byte, error) {
		return nil, nil, fmt.Errorf("registry not available on this platform")
	}
}
