//go:build windows

package navigator

import (
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	_user32 = windows.NewLazySystemDLL("user32.dll")

	_isWindow              = _user32.NewProc("IsWindow")
	_isIconic              = _user32.NewProc("IsIconic")
	_showWindow            = _user32.NewProc("ShowWindow")
	_setForegroundWindow   = _user32.NewProc("SetForegroundWindow")
	_getForegroundWindow   = _user32.NewProc("GetForegroundWindow")
	_getWindowThreadProcID = _user32.NewProc("GetWindowThreadProcessId")
	_getCursorPos          = _user32.NewProc("GetCursorPos")
	_monitorFromPoint      = _user32.NewProc("MonitorFromPoint")
	_getMonitorInfoW       = _user32.NewProc("GetMonitorInfoW")
)

const (
	_SW_RESTORE              = 9
	_MONITOR_DEFAULTTONEAREST = 2
)

// ActivateWindow restores (if minimized) and foregrounds hwnd.
// Returns true on success, false if the window no longer exists or activation failed.
func ActivateWindow(hwnd uintptr) bool {
	ok, _, _ := _isWindow.Call(hwnd)
	if ok == 0 {
		return false
	}
	iconic, _, _ := _isIconic.Call(hwnd)
	if iconic != 0 {
		_showWindow.Call(hwnd, _SW_RESTORE)
	}
	r, _, _ := _setForegroundWindow.Call(hwnd)
	return r != 0
}

// ForceForeground brings hwnd to the foreground.
// WM_HOTKEY is exempt from the foreground-lock timeout so a plain SetForegroundWindow is
// sufficient after RegisterHotKey fires — no AttachThreadInput needed or wanted (merging
// input queues corrupts cursor state on the detached thread).
func ForceForeground(hwnd uintptr) {
	_setForegroundWindow.Call(hwnd)
}

// Rect is a Win32 RECT structure.
type Rect struct{ Left, Top, Right, Bottom int32 }

// monitorInfo is the Win32 MONITORINFO structure.
type monitorInfo struct {
	cbSize    uint32
	rcMonitor Rect
	rcWork    Rect
	dwFlags   uint32
}

// GetCursorMonitorWorkArea returns (left, top, right, bottom) of the work area
// of the monitor under the cursor. Falls back to {0, 0, 1920, 1080} on failure.
func GetCursorMonitorWorkArea() (left, top, right, bottom int) {
	type point struct{ x, y int32 }
	var pt point
	_getCursorPos.Call(uintptr(unsafe.Pointer(&pt)))
	hMonitor, _, _ := _monitorFromPoint.Call(
		uintptr(pt.x),
		uintptr(pt.y),
		_MONITOR_DEFAULTTONEAREST,
	)
	if hMonitor == 0 {
		return 0, 0, 1920, 1080
	}
	var info monitorInfo
	info.cbSize = uint32(unsafe.Sizeof(info))
	_getMonitorInfoW.Call(hMonitor, uintptr(unsafe.Pointer(&info)))
	r := info.rcWork
	return int(r.Left), int(r.Top), int(r.Right), int(r.Bottom)
}
