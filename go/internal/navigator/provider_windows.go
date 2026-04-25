//go:build windows

package navigator

import (
	"image"
	"path/filepath"
	"regexp"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
)

// _notifTitleRE matches "(N)" prefix in window titles (e.g. "(3) Inbox").
var _notifTitleRE = regexp.MustCompile(`^\(\d+\)`)

// _excludedProcesses lists process names never shown in the switcher (lowercase).
var _excludedProcesses = map[string]struct{}{
	"textinputhost.exe": {},
}

var (
	_gdi32    = windows.NewLazySystemDLL("gdi32.dll")
	_shell32  = windows.NewLazySystemDLL("shell32.dll")
	_advapi32 = windows.NewLazySystemDLL("advapi32.dll")

	_enumWindows              = _user32.NewProc("EnumWindows")
	_isWindowVisible          = _user32.NewProc("IsWindowVisible")
	_getWindowLong            = _user32.NewProc("GetWindowLongW")
	_getWindowText            = _user32.NewProc("GetWindowTextW")
	_sendMessage              = _user32.NewProc("SendMessageW")
	_getClassLong             = _user32.NewProc("GetClassLongW")
	_getDC                    = _user32.NewProc("GetDC")
	_releaseDC                = _user32.NewProc("ReleaseDC")
	_drawIconEx               = _user32.NewProc("DrawIconEx")
	_destroyIcon              = _user32.NewProc("DestroyIcon")
	_createDIBSection         = _gdi32.NewProc("CreateDIBSection")
	_createCompatibleDC       = _gdi32.NewProc("CreateCompatibleDC")
	_selectObject             = _gdi32.NewProc("SelectObject")
	_deleteObject             = _gdi32.NewProc("DeleteObject")
	_deleteDC                 = _gdi32.NewProc("DeleteDC")
	_sHGetFileInfoW           = _shell32.NewProc("SHGetFileInfoW")
	_queryFullProcessImageName = windows.NewLazySystemDLL("kernel32.dll").NewProc("QueryFullProcessImageNameW")
)

const (
	_WS_EX_TOOLWINDOW = 0x00000080
	_GWL_EXSTYLE      = ^uintptr(19) // -20
	_WM_GETICON       = 0x007F
	_ICON_BIG         = 1
	_ICON_SMALL       = 0
	_GCL_HICON        = ^uintptr(13) // -14
	_SHGFI_ICON       = 0x000000100
	_SHGFI_LARGEICON  = 0x000000000
	_DI_NORMAL        = 0x0003
	_BI_RGB           = 0
)

// bitmapInfoHeader is a BITMAPINFOHEADER structure.
type bitmapInfoHeader struct {
	biSize          uint32
	biWidth         int32
	biHeight        int32
	biPlanes        uint16
	biBitCount      uint16
	biCompression   uint32
	biSizeImage     uint32
	biXPelsPerMeter int32
	biYPelsPerMeter int32
	biClrUsed       uint32
	biClrImportant  uint32
}

// shFileInfo is a SHFILEINFOW structure.
type shFileInfo struct {
	hIcon         uintptr
	iIcon         int32
	dwAttributes  uint32
	szDisplayName [260]uint16
	szTypeName    [80]uint16
}

// queryExePath resolves the exe path for a process handle.
func queryExePath(handle windows.Handle) string {
	buf := make([]uint16, 1024)
	size := uint32(len(buf))
	_queryFullProcessImageName.Call(uintptr(handle), 0, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&size)))
	return windows.UTF16ToString(buf[:size])
}

// shGetFileInfoIcon gets a window's icon via SHGetFileInfoW (fallback for UWP/modern apps).
// Returns the HICON handle (caller-owned, must DestroyIcon).
func shGetFileInfoIcon(hwnd uintptr) uintptr {
	var dummy uint32
	_, _, _ = _getWindowThreadProcID.Call(hwnd, uintptr(unsafe.Pointer(&dummy)))
	pid := dummy

	handle, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
	if err != nil {
		return 0
	}
	exePath := queryExePath(handle)
	windows.CloseHandle(handle)
	if exePath == "" {
		return 0
	}
	exeW, _ := windows.UTF16PtrFromString(exePath)
	var info shFileInfo
	r, _, _ := _sHGetFileInfoW.Call(
		uintptr(unsafe.Pointer(exeW)),
		0,
		uintptr(unsafe.Pointer(&info)),
		uintptr(unsafe.Sizeof(info)),
		_SHGFI_ICON|_SHGFI_LARGEICON,
	)
	if r == 0 {
		return 0
	}
	return info.hIcon
}

// ExtractIcon extracts a 32×32 RGBA icon for hwnd. Returns FallbackIcon() on failure.
func ExtractIcon(hwnd uintptr) *image.RGBA {
	const w, h = IconSize, IconSize

	ownedIcon := false
	iconHandle, _, _ := _sendMessage.Call(hwnd, _WM_GETICON, _ICON_BIG, 0)
	if iconHandle == 0 {
		iconHandle, _, _ = _sendMessage.Call(hwnd, _WM_GETICON, _ICON_SMALL, 0)
	}
	if iconHandle == 0 {
		iconHandle, _, _ = _getClassLong.Call(hwnd, _GCL_HICON)
	}
	if iconHandle == 0 {
		iconHandle = shGetFileInfoIcon(hwnd)
		ownedIcon = iconHandle != 0
	}
	if iconHandle == 0 {
		return FallbackIcon()
	}

	bmih := bitmapInfoHeader{
		biSize:     uint32(unsafe.Sizeof(bitmapInfoHeader{})),
		biWidth:    w,
		biHeight:   -h, // negative = top-down DIB
		biPlanes:   1,
		biBitCount: 32,
	}

	hdcScreen, _, _ := _getDC.Call(0)
	var pixelsPtr uintptr
	hbmp, _, _ := _createDIBSection.Call(
		hdcScreen,
		uintptr(unsafe.Pointer(&bmih)),
		0,
		uintptr(unsafe.Pointer(&pixelsPtr)),
		0, 0,
	)
	_releaseDC.Call(0, hdcScreen)

	if hbmp == 0 || pixelsPtr == 0 {
		if ownedIcon {
			_destroyIcon.Call(iconHandle)
		}
		return FallbackIcon()
	}

	hdcMem, _, _ := _createCompatibleDC.Call(0)
	oldBmp, _, _ := _selectObject.Call(hdcMem, hbmp)
	_drawIconEx.Call(hdcMem, 0, 0, iconHandle, w, h, 0, 0, _DI_NORMAL)

	// Copy raw BGRA pixels into a Go slice
	rawBuf := make([]byte, w*h*4)
	for i := range rawBuf {
		rawBuf[i] = *(*byte)(unsafe.Pointer(pixelsPtr + uintptr(i)))
	}

	_selectObject.Call(hdcMem, oldBmp)
	_deleteDC.Call(hdcMem)
	_deleteObject.Call(hbmp)
	if ownedIcon {
		_destroyIcon.Call(iconHandle)
	}

	// Convert BGRA → RGBA
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for i := 0; i < w*h; i++ {
		b, g, r, a := rawBuf[i*4], rawBuf[i*4+1], rawBuf[i*4+2], rawBuf[i*4+3]
		img.Pix[i*4] = r
		img.Pix[i*4+1] = g
		img.Pix[i*4+2] = b
		img.Pix[i*4+3] = a
	}
	return img
}

// getProcessName returns the exe basename for hwnd.
func getProcessName(hwnd uintptr) string {
	var dummy uint32
	_, _, _ = _getWindowThreadProcID.Call(hwnd, uintptr(unsafe.Pointer(&dummy)))
	pid := dummy
	handle, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
	if err != nil {
		return ""
	}
	exePath := queryExePath(handle)
	windows.CloseHandle(handle)
	return filepath.Base(exePath)
}

// getWindowTitle returns the window title for hwnd.
func getWindowTitle(hwnd uintptr) string {
	buf := make([]uint16, 512)
	n, _, _ := _getWindowText.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	return windows.UTF16ToString(buf[:n])
}

// RealWindowProvider enumerates windows using the Win32 API.
type RealWindowProvider struct {
	AssignDesktops DesktopAssigner
	IsFlashing     func(uintptr) bool // returns true if hwnd has an active notification
	ExtraFilters   []WindowFilter
}

// NewRealWindowProvider creates a RealWindowProvider with sensible defaults.
// isFlashing may be nil (all windows treated as non-flashing).
func NewRealWindowProvider(assign DesktopAssigner, isFlashing func(uintptr) bool, extra []WindowFilter) *RealWindowProvider {
	if assign == nil {
		assign = func(hwnds []uintptr) (map[uintptr]int, map[uintptr]bool) {
			return AssignDesktopNumbers(hwnds, DefaultVirtualDesktopManager(), GetRegistryDesktopOrder(DefaultRegistryDesktopReader()))
		}
	}
	return &RealWindowProvider{AssignDesktops: assign, IsFlashing: isFlashing, ExtraFilters: extra}
}

// GetWindows enumerates visible non-tool windows in z-order.
func (p *RealWindowProvider) GetWindows() []WindowInfo {
	var hwnds []uintptr

	cb := windows.NewCallback(func(hwnd windows.HWND, _ uintptr) uintptr {
		h := uintptr(hwnd)
		vis, _, _ := _isWindowVisible.Call(h)
		if vis == 0 {
			return 1
		}
		exStyle, _, _ := _getWindowLong.Call(h, _GWL_EXSTYLE)
		if exStyle&_WS_EX_TOOLWINDOW != 0 {
			return 1
		}
		title := getWindowTitle(h)
		if title == "" {
			return 1
		}
		hwnds = append(hwnds, h)
		return 1
	})
	_enumWindows.Call(cb, 0)

	numbers, isCurrentMap := p.AssignDesktops(hwnds)

	var results []WindowInfo
	for _, hwnd := range hwnds {
		if numbers[hwnd] == -1 {
			continue
		}
		title := getWindowTitle(hwnd)
		processName := getProcessName(hwnd)
		if _, excluded := _excludedProcesses[strings.ToLower(processName)]; excluded {
			continue
		}
		skip := false
		for _, f := range p.ExtraFilters {
			if !f(hwnd, title, processName) {
				skip = true
				break
			}
		}
		if skip {
			continue
		}
		inFlashing := p.IsFlashing != nil && p.IsFlashing(hwnd)
		hasNotif := inFlashing || _notifTitleRE.MatchString(title)

		results = append(results, WindowInfo{
			HWND:             hwnd,
			Title:            title,
			ProcessName:      processName,
			DesktopNumber:    numbers[hwnd],
			IsCurrentDesktop: isCurrentMap[hwnd],
			HasNotification:  hasNotif,
		})
	}
	return results
}

