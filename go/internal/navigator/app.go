package navigator

import (
	"sync"
	"time"
)

// moveCmd carries a hotkey-triggered window-move request.
type moveCmd struct {
	hwnd      uintptr
	direction int // +1 right, -1 left
}

// NotificationSet is a goroutine-safe set of HWNDs that have a visible notification.
type NotificationSet struct {
	mu sync.RWMutex
	m  map[uintptr]struct{}
}

// NewNotificationSet creates an empty NotificationSet.
func NewNotificationSet() *NotificationSet {
	return &NotificationSet{m: make(map[uintptr]struct{})}
}

// Add marks hwnd as having an active notification.
func (s *NotificationSet) Add(hwnd uintptr) {
	s.mu.Lock()
	s.m[hwnd] = struct{}{}
	s.mu.Unlock()
}

// Remove clears the notification state for hwnd.
func (s *NotificationSet) Remove(hwnd uintptr) {
	s.mu.Lock()
	delete(s.m, hwnd)
	s.mu.Unlock()
}

// Contains reports whether hwnd currently has a notification.
func (s *NotificationSet) Contains(hwnd uintptr) bool {
	s.mu.RLock()
	_, ok := s.m[hwnd]
	s.mu.RUnlock()
	return ok
}

// mainLoop is the central coordinator.  It blocks until quitCh is closed.
func mainLoop(
	provider WindowProvider,
	overlay Overlay,
	tray TrayIconBackend,
	switcher DesktopSwitcher,
	regReader RegistryDesktopReader,
	showCh <-chan struct{},
	moveCh <-chan moveCmd,
	quitCh <-chan struct{},
) {
	initialDesktop := GetCurrentDesktopNumber(regReader)
	tray.Start(initialDesktop)
	currentDesktop := initialDesktop

	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-showCh:
			// Drain any additional pending signals (debounce rapid hotkey presses).
			for len(showCh) > 0 {
				<-showCh
			}
			wins := provider.GetWindows()
			desktop := 0
			for _, w := range wins {
				if w.IsCurrentDesktop && w.DesktopNumber > 0 {
					desktop = w.DesktopNumber
					break
				}
			}
			overlay.Show(wins, desktop)
			tray.Update(desktop)
			if desktop > 0 {
				currentDesktop = desktop
			}

		case mv := <-moveCh:
			targetN := MoveWindowToAdjacentDesktop(
				mv.hwnd,
				mv.direction,
				switcher,
				func() []string { return GetRegistryDesktopOrder(regReader) },
				func() int { return GetCurrentDesktopNumber(regReader) },
			)
			if targetN > 0 {
				currentDesktop = targetN
				tray.Update(targetN)
			}

		case <-ticker.C:
			n := GetCurrentDesktopNumber(regReader)
			if n > 0 && n != currentDesktop {
				currentDesktop = n
				tray.Update(n)
			}

		case <-quitCh:
			tray.Stop()
			return
		}
	}
}
