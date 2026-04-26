//go:build windows

package navigator

import (
	"os"
	"os/signal"
	"regexp"
	"runtime"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
)

// ---------------------------------------------------------------------------
// Win32 proc declarations (app-specific)
// ---------------------------------------------------------------------------

var (
	_registerWindowMessageW  = _user32.NewProc("RegisterWindowMessageW")
	_registerShellHookWindow = _user32.NewProc("RegisterShellHookWindow")
	_deregShellHookWindow    = _user32.NewProc("DeregisterShellHookWindow")
	_registerHotKey          = _user32.NewProc("RegisterHotKey")
	_unregisterHotKey        = _user32.NewProc("UnregisterHotKey")

	_kernel32               = windows.NewLazySystemDLL("kernel32.dll")
	_getConsoleProcessList  = _kernel32.NewProc("GetConsoleProcessList")
	_getConsoleWindow       = _kernel32.NewProc("GetConsoleWindow")

	_shcore                 = windows.NewLazySystemDLL("shcore.dll")
	_setProcessDpiAwareness = _shcore.NewProc("SetProcessDpiAwareness")
)

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const (
	_hotkeyMsg = uint32(0x0312) // WM_HOTKEY

	// Hotkey modifiers
	_modCtrl  = uintptr(0x0002) // MOD_CONTROL
	_modShift = uintptr(0x0004) // MOD_SHIFT
	_modWin   = uintptr(0x0008) // MOD_WIN

	// Virtual keys for hotkeys
	_vkSpace    = uintptr(0x20) // VK_SPACE
	_vkLeftArr  = uintptr(0x25) // VK_LEFT
	_vkRightArr = uintptr(0x27) // VK_RIGHT

	// Hotkey IDs (must not conflict with IDs in other threads)
	_hotkeyShow  = uintptr(100)
	_hotkeyLeft  = uintptr(101)
	_hotkeyRight = uintptr(102)

	// Shell hook notification codes (WPARAM values on WM_SHELL messages)
	_hshellActivated    = uintptr(4)
	_hshellDestroyed    = uintptr(2)
	_hshellRedraw       = uintptr(6)
	_hshellFlash        = uintptr(0x8006) // HSHELL_REDRAW | HSHELL_HIGHBIT — FlashWindowEx
	_hshellRudeActivated = uintptr(0x8004)
)

var _flashNotifRE = regexp.MustCompile(`^\(\d+\)`)

// ---------------------------------------------------------------------------
// Console visibility
// ---------------------------------------------------------------------------

// hideConsoleIfStandalone hides the console window when this process is the
// only one attached to it — meaning we were launched by double-click or a
// startup entry rather than from a terminal.  When launched from a terminal
// (cmd, PowerShell, WSL) more than one process shares the console, so we
// leave it alone: the console is the terminal's window, not ours to hide, and
// keeping it attached is what makes Ctrl+C reach this process.
//
// Must be called before any window or COM initialisation so the console window
// disappears before anything else becomes visible.
func hideConsoleIfStandalone() {
	var pids [2]uint32
	n, _, _ := _getConsoleProcessList.Call(uintptr(unsafe.Pointer(&pids[0])), 2)
	if n != 1 {
		return // shared console — launched from a terminal
	}
	if cw, _, _ := _getConsoleWindow.Call(); cw != 0 {
		_showWindow.Call(cw, 0) // SW_HIDE
	}
}

// ---------------------------------------------------------------------------
// DPI awareness
// ---------------------------------------------------------------------------

// SetDpiAwareness enables per-monitor v2 DPI awareness.
// Must be called before any window is created.
func SetDpiAwareness() {
	_setProcessDpiAwareness.Call(2) // PROCESS_PER_MONITOR_DPI_AWARE_V2
}

// ---------------------------------------------------------------------------
// Flash monitor
// ---------------------------------------------------------------------------

// StartFlashMonitor monitors the shell for notification signals (FlashWindowEx,
// ITaskbarList3::SetOverlayIcon) and updates s accordingly.
// Runs in a dedicated goroutine.
func StartFlashMonitor(s *NotificationSet) {
	go flashMonitorLoop(s)
}

func flashMonitorLoop(s *NotificationSet) {
	runtime.LockOSThread()

	hInst, _, _ := _getModuleHandleW.Call(0)
	clsName, _ := windows.UTF16PtrFromString("WinNavFlashMon")

	proc := windows.NewCallback(func(h windows.HWND, m uint32, wp, lp uintptr) uintptr {
		r, _, _ := _defWindowProcW.Call(uintptr(h), uintptr(m), wp, lp)
		return r
	})

	wcx := wndClassExW{
		cbSize:        uint32(unsafe.Sizeof(wndClassExW{})),
		lpfnWndProc:   proc,
		hInstance:     hInst,
		lpszClassName: clsName,
	}
	_registerClassExW.Call(uintptr(unsafe.Pointer(&wcx)))

	const hwndMessage = ^uintptr(2) // (HWND)(LONG_PTR)(-3) — message-only window
	hwnd, _, _ := _createWindowExW.Call(
		0, uintptr(unsafe.Pointer(clsName)), 0, 0,
		0, 0, 0, 0,
		hwndMessage, 0, hInst, 0,
	)
	if hwnd == 0 {
		return
	}

	shellName, _ := windows.UTF16PtrFromString("SHELLHOOK")
	wmShell, _, _ := _registerWindowMessageW.Call(uintptr(unsafe.Pointer(shellName)))
	_registerShellHookWindow.Call(hwnd)

	// Seed the title cache so pre-existing overlay icons are detected on the first redraw.
	titles := make(map[uintptr]string)
	seedCB := windows.NewCallback(func(h windows.HWND, _ uintptr) uintptr {
		vis, _, _ := _isWindowVisible.Call(uintptr(h))
		if vis != 0 {
			titles[uintptr(h)] = getWindowTitle(uintptr(h))
		}
		return 1
	})
	_enumWindows.Call(seedCB, 0)

	var msg msgStruct
	for {
		r, _, _ := _getMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
		if r == 0 || r == ^uintptr(0) {
			break
		}
		if msg.message == uint32(wmShell) {
			target := msg.lParam // shell hook: LPARAM holds the target HWND
			switch msg.wParam {
			case _hshellFlash:
				s.Add(target)
			case _hshellRedraw:
				current := getWindowTitle(target)
				prev, known := titles[target]
				titles[target] = current
				if !known || current != prev {
					// First time or title changed — check for "(N)" badge pattern.
					if _flashNotifRE.MatchString(current) {
						s.Add(target)
					}
				} else {
					// Same title, seen before — background redraw signals overlay icon change.
					fg, _, _ := _getForegroundWindow.Call()
					if fg != target {
						s.Add(target)
					}
				}
			case _hshellActivated, _hshellRudeActivated:
				s.Remove(target)
			case _hshellDestroyed:
				s.Remove(target)
				delete(titles, target)
			}
		}
		_dispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}

	_deregShellHookWindow.Call(hwnd)
	_destroyWindowProc.Call(hwnd)
}

// ---------------------------------------------------------------------------
// Overlay hotkey listener (Ctrl+Shift+Space)
// ---------------------------------------------------------------------------

// StartOverlayHotkeyListener registers Ctrl+Shift+Space via RegisterHotKey and
// sends to ch each time it fires.  Runs in a dedicated goroutine.
func StartOverlayHotkeyListener(ch chan<- struct{}) {
	go overlayHotkeyLoop(ch)
}

func overlayHotkeyLoop(ch chan<- struct{}) {
	runtime.LockOSThread()

	r, _, _ := _registerHotKey.Call(0, _hotkeyShow, _modCtrl|_modShift, _vkSpace)
	if r == 0 {
		return
	}
	defer _unregisterHotKey.Call(0, _hotkeyShow)

	var msg msgStruct
	for {
		r, _, _ := _getMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
		if r == 0 || r == ^uintptr(0) {
			break
		}
		if msg.message == _hotkeyMsg && msg.wParam == _hotkeyShow {
			select {
			case ch <- struct{}{}:
			default: // drop if channel is full
			}
		}
		_dispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}
}

// ---------------------------------------------------------------------------
// Move hotkey listener (Ctrl+Win+Shift+Left / Right)
// ---------------------------------------------------------------------------

// StartMoveHotkeyListener registers Ctrl+Win+Shift+Left/Right via RegisterHotKey
// and sends to ch each time either fires.  Runs in a dedicated goroutine.
func StartMoveHotkeyListener(ch chan<- moveCmd) {
	go moveHotkeyLoop(ch)
}

func moveHotkeyLoop(ch chan<- moveCmd) {
	runtime.LockOSThread()

	okLeft, _, _ := _registerHotKey.Call(0, _hotkeyLeft, _modCtrl|_modShift|_modWin, _vkLeftArr)
	okRight, _, _ := _registerHotKey.Call(0, _hotkeyRight, _modCtrl|_modShift|_modWin, _vkRightArr)

	defer func() {
		if okLeft != 0 {
			_unregisterHotKey.Call(0, _hotkeyLeft)
		}
		if okRight != 0 {
			_unregisterHotKey.Call(0, _hotkeyRight)
		}
	}()

	var msg msgStruct
	for {
		r, _, _ := _getMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
		if r == 0 || r == ^uintptr(0) {
			break
		}
		if msg.message == _hotkeyMsg {
			fg, _, _ := _getForegroundWindow.Call()
			var dir int
			switch msg.wParam {
			case _hotkeyLeft:
				dir = -1
			case _hotkeyRight:
				dir = +1
			}
			if dir != 0 {
				select {
				case ch <- moveCmd{hwnd: fg, direction: dir}:
				default:
				}
			}
		}
		_dispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}
}

// ---------------------------------------------------------------------------
// RunApp — wires up all Windows defaults and runs the application
// ---------------------------------------------------------------------------

// RunApp sets up DPI awareness, starts background services, and runs the
// main event loop.  Blocks until the user exits via the tray icon or Ctrl+C.
func RunApp() {
	// Must be first: hides the console window before anything else is visible
	// when launched standalone (double-click / startup entry).
	hideConsoleIfStandalone()

	InitDebugLog()

	// Lock this goroutine to its OS thread before CoInitializeEx so that all
	// IVirtualDesktopManager vtable calls (in AssignDesktopNumbers) happen on
	// the same thread that initialized the STA.  Go goroutines may otherwise
	// migrate between OS threads, leaving COM with an uninitialized apartment.
	runtime.LockOSThread()

	SetDpiAwareness()

	notifs := NewNotificationSet()
	StartFlashMonitor(notifs)

	showCh := make(chan struct{}, 10)
	moveCh := make(chan moveCmd, 10)
	StartOverlayHotkeyListener(showCh)
	StartMoveHotkeyListener(moveCh)

	quitCh := make(chan struct{})
	var once sync.Once
	quit := func() { once.Do(func() { close(quitCh) }) }

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt)
	defer signal.Stop(sigCh)
	go func() {
		<-sigCh
		quit()
	}()

	regReader := DefaultRegistryDesktopReader()
	switcher := DefaultDesktopSwitcher()
	manager := DefaultVirtualDesktopManager()

	provider := NewRealWindowProvider(
		func(hwnds []uintptr) (map[uintptr]int, map[uintptr]bool) {
			return AssignDesktopNumbers(hwnds, manager, GetRegistryDesktopOrder(regReader))
		},
		notifs.Contains,
		nil,
	)

	tray := NewTrayIcon(quit)

	overlay := NewOverlay(OverlayCallbacks{
		OnActivate: func(hwnd uintptr) { ActivateWindow(hwnd) },
		OnMove: func(hwnd uintptr) {
			_ = switcher.MoveWindowToCurrent(hwnd)
			ActivateWindow(hwnd)
		},
	})

	mainLoop(provider, overlay, tray, switcher, regReader, showCh, moveCh, quitCh)
}
