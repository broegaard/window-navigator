//go:build windows

package navigator

import (
	"image"
	"runtime"
	"sync/atomic"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	_shellNotifyIconW   = windows.NewLazySystemDLL("shell32.dll").NewProc("Shell_NotifyIconW")
	_createPopupMenu    = _user32.NewProc("CreatePopupMenu")
	_appendMenuW        = _user32.NewProc("AppendMenuW")
	_trackPopupMenu     = _user32.NewProc("TrackPopupMenu")
	_destroyMenu        = _user32.NewProc("DestroyMenu")
	_postMessageW       = _user32.NewProc("PostMessageW")
	_defWindowProcW     = _user32.NewProc("DefWindowProcW")
	_registerClassExW   = _user32.NewProc("RegisterClassExW")
	_createWindowExW    = _user32.NewProc("CreateWindowExW")
	_destroyWindowProc  = _user32.NewProc("DestroyWindow")
	_getMessageW        = _user32.NewProc("GetMessageW")
	_translateMessage   = _user32.NewProc("TranslateMessage")
	_dispatchMessageW   = _user32.NewProc("DispatchMessageW")
	_postQuitMessage    = _user32.NewProc("PostQuitMessage")
	_unregisterClassW   = _user32.NewProc("UnregisterClassW")
	_getModuleHandleW   = windows.NewLazySystemDLL("kernel32.dll").NewProc("GetModuleHandleW")
	_createFontW        = _gdi32.NewProc("CreateFontW")
	_setTextColor       = _gdi32.NewProc("SetTextColor")
	_setBkMode          = _gdi32.NewProc("SetBkMode")
	_drawTextW          = _user32.NewProc("DrawTextW")
	_createBitmap       = _gdi32.NewProc("CreateBitmap")
	_createIconIndirect = _user32.NewProc("CreateIconIndirect")
)

const (
	_NIM_ADD        = uintptr(0)
	_NIM_MODIFY     = uintptr(1)
	_NIM_DELETE     = uintptr(2)
	_NIF_MESSAGE    = uint32(0x1)
	_NIF_ICON       = uint32(0x2)
	_NIF_TIP        = uint32(0x4)
	_WM_TRAYNOTIFY  = uint32(0x8000 + 1) // WM_APP + 1
	_WM_TRAY_UPDATE = uint32(0x8000 + 2) // WM_APP + 2
	_WM_TRAY_STOP   = uint32(0x8000 + 3) // WM_APP + 3
	_WM_RBUTTONUP   = uint32(0x0205)
	_IDM_EXIT       = uintptr(1000)
	_MF_STRING      = uintptr(0x0)
	_MF_GRAYED      = uintptr(0x1)
	_MF_SEPARATOR   = uintptr(0x800)
	_TPM_RIGHTALIGN = uintptr(0x0008)
	_TPM_BOTTOMALIGN = uintptr(0x0020)
	_TPM_NONOTIFY   = uintptr(0x0080)
	_TPM_RETURNCMD  = uintptr(0x0100)
	_FW_BOLD        = uintptr(700)
	_TRANSPARENT    = uintptr(1)
	_DT_CENTER      = uintptr(0x1)
	_DT_VCENTER     = uintptr(0x4)
	_DT_SINGLELINE  = uintptr(0x20)
)

// notifyIconData mirrors NOTIFYICONDATAW (v1 fields only).
type notifyIconData struct {
	cbSize           uint32
	hWnd             uintptr
	uID              uint32
	uFlags           uint32
	uCallbackMessage uint32
	hIcon            uintptr
	szTip            [128]uint16
}

// iconInfoStruct mirrors ICONINFO.
type iconInfoStruct struct {
	fIcon    uint32
	xHotspot uint32
	yHotspot uint32
	hbmMask  uintptr
	hbmColor uintptr
}

// wndClassExW mirrors WNDCLASSEXW.
type wndClassExW struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

// msgStruct mirrors MSG.
type msgStruct struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	ptX     int32
	ptY     int32
}

// makeHICON builds an HICON from an *image.RGBA background with a centered bold label.
func makeHICON(img *image.RGBA, label string) uintptr {
	size := img.Bounds().Dx()

	// Convert RGBA → BGRA (top-down)
	buf := make([]byte, size*size*4)
	for y := 0; y < size; y++ {
		for x := 0; x < size; x++ {
			src := img.PixOffset(x, y)
			dst := y*size*4 + x*4
			buf[dst+0] = img.Pix[src+2] // B
			buf[dst+1] = img.Pix[src+1] // G
			buf[dst+2] = img.Pix[src+0] // R
			buf[dst+3] = img.Pix[src+3] // A
		}
	}

	bmih := bitmapInfoHeader{
		biSize:     uint32(unsafe.Sizeof(bitmapInfoHeader{})),
		biWidth:    int32(size),
		biHeight:   -int32(size), // top-down
		biPlanes:   1,
		biBitCount: 32,
	}
	hdcScreen, _, _ := _getDC.Call(0)
	var pixPtr uintptr
	hbm, _, _ := _createDIBSection.Call(
		hdcScreen,
		uintptr(unsafe.Pointer(&bmih)),
		0,
		uintptr(unsafe.Pointer(&pixPtr)),
		0, 0,
	)
	_releaseDC.Call(0, hdcScreen)
	if hbm == 0 || pixPtr == 0 {
		return 0
	}

	for i, b := range buf {
		*(*byte)(unsafe.Pointer(pixPtr + uintptr(i))) = b
	}

	// Draw bold white text with black outline via GDI
	hdcMem, _, _ := _createCompatibleDC.Call(0)
	old, _, _ := _selectObject.Call(hdcMem, hbm)

	fontSize := uintptr(40)
	if len(label) == 1 {
		fontSize = 54
	}
	faceName, _ := windows.UTF16PtrFromString("Segoe UI")
	hFont, _, _ := _createFontW.Call(
		fontSize, 0, 0, 0, _FW_BOLD,
		0, 0, 0, 0, 0, 0, 0, 0,
		uintptr(unsafe.Pointer(faceName)),
	)
	oldFont, _, _ := _selectObject.Call(hdcMem, hFont)
	_setBkMode.Call(hdcMem, _TRANSPARENT)

	type rect32 struct{ l, t, r, b int32 }
	labelW, _ := windows.UTF16PtrFromString(label)
	sz := int32(size)
	drawLabel := func(dx, dy int32, color uint32) {
		rc := rect32{dx, dy, sz + dx, sz + dy}
		_setTextColor.Call(hdcMem, uintptr(color))
		_drawTextW.Call(
			hdcMem,
			uintptr(unsafe.Pointer(labelW)),
			^uintptr(0),
			uintptr(unsafe.Pointer(&rc)),
			_DT_CENTER|_DT_VCENTER|_DT_SINGLELINE,
		)
	}
	// Black outline at four diagonal offsets, then white fill on top
	drawLabel(-1, -1, 0x00000000)
	drawLabel(+1, -1, 0x00000000)
	drawLabel(-1, +1, 0x00000000)
	drawLabel(+1, +1, 0x00000000)
	drawLabel(0, 0, 0x00FFFFFF)

	_selectObject.Call(hdcMem, oldFont)
	_deleteObject.Call(hFont)
	_selectObject.Call(hdcMem, old)
	_deleteDC.Call(hdcMem)

	// GDI DrawText destroys alpha; restore it
	for i := 3; i < size*size*4; i += 4 {
		*(*byte)(unsafe.Pointer(pixPtr + uintptr(i))) = 255
	}

	// 1-bpp AND mask, all zeros → color bitmap alpha drives opacity
	maskLen := ((size * size) + 7) / 8
	maskBuf := make([]byte, maskLen)
	hMask, _, _ := _createBitmap.Call(
		uintptr(size), uintptr(size), 1, 1,
		uintptr(unsafe.Pointer(&maskBuf[0])),
	)

	ii := iconInfoStruct{fIcon: 1, hbmMask: hMask, hbmColor: hbm}
	hIcon, _, _ := _createIconIndirect.Call(uintptr(unsafe.Pointer(&ii)))

	_deleteObject.Call(hMask)
	_deleteObject.Call(hbm)
	return hIcon
}

func trayLabel(n int) string {
	if n > 0 && n <= 9 {
		return string(rune('0' + n))
	}
	if n > 9 {
		return "+"
	}
	return "W"
}

// windowsTrayIcon implements TrayIconBackend using Shell_NotifyIconW.
type windowsTrayIcon struct {
	onExit  func()
	hwnd    atomic.Uintptr
	curIcon atomic.Uintptr
}

// Start launches the tray message loop in a dedicated goroutine and returns immediately.
func (t *windowsTrayIcon) Start(desktopNumber int) {
	go t.loop(desktopNumber)
}

// Update sends a message to the tray loop goroutine to refresh the icon.
func (t *windowsTrayIcon) Update(desktopNumber int) {
	if hwnd := t.hwnd.Load(); hwnd != 0 {
		_postMessageW.Call(hwnd, uintptr(_WM_TRAY_UPDATE), uintptr(desktopNumber), 0)
	}
}

// Stop posts WM_TRAY_STOP so the loop goroutine exits.
func (t *windowsTrayIcon) Stop() {
	if hwnd := t.hwnd.Load(); hwnd != 0 {
		_postMessageW.Call(hwnd, uintptr(_WM_TRAY_STOP), 0, 0)
	}
}

func (t *windowsTrayIcon) loop(desktopNumber int) {
	runtime.LockOSThread()

	hInst, _, _ := _getModuleHandleW.Call(0)
	clsName, _ := windows.UTF16PtrFromString("WinNavTray")

	proc := windows.NewCallback(func(h windows.HWND, m uint32, wp, lp uintptr) uintptr {
		return t.wndProc(uintptr(h), m, wp, lp)
	})

	wcx := wndClassExW{
		cbSize:        uint32(unsafe.Sizeof(wndClassExW{})),
		lpfnWndProc:   proc,
		hInstance:     hInst,
		lpszClassName: clsName,
	}
	_registerClassExW.Call(uintptr(unsafe.Pointer(&wcx)))

	const hwndMessage = ^uintptr(2) // (HWND)-3
	hwnd, _, _ := _createWindowExW.Call(
		0,
		uintptr(unsafe.Pointer(clsName)),
		0, 0,
		0, 0, 0, 0,
		hwndMessage, 0, hInst, 0,
	)
	t.hwnd.Store(hwnd)

	img := MakeTrayIcon(desktopNumber)
	hIcon := makeHICON(img, trayLabel(desktopNumber))
	t.curIcon.Store(hIcon)

	tip := [128]uint16{}
	copy(tip[:], windows.StringToUTF16("Windows Navigator"))

	nid := notifyIconData{
		cbSize:           uint32(unsafe.Sizeof(notifyIconData{})),
		hWnd:             hwnd,
		uID:              1,
		uFlags:           _NIF_MESSAGE | _NIF_ICON | _NIF_TIP,
		uCallbackMessage: _WM_TRAYNOTIFY,
		hIcon:            hIcon,
		szTip:            tip,
	}
	_shellNotifyIconW.Call(_NIM_ADD, uintptr(unsafe.Pointer(&nid)))

	var m msgStruct
	for {
		r, _, _ := _getMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if r == 0 || r == ^uintptr(0) {
			break
		}
		_translateMessage.Call(uintptr(unsafe.Pointer(&m)))
		_dispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}

	nidDel := notifyIconData{cbSize: uint32(unsafe.Sizeof(notifyIconData{})), hWnd: hwnd, uID: 1}
	_shellNotifyIconW.Call(_NIM_DELETE, uintptr(unsafe.Pointer(&nidDel)))
	if old := t.curIcon.Load(); old != 0 {
		_destroyIcon.Call(old)
	}
	_destroyWindowProc.Call(hwnd)
	_unregisterClassW.Call(uintptr(unsafe.Pointer(clsName)), hInst)
}

func (t *windowsTrayIcon) wndProc(hwnd uintptr, message uint32, wp, lp uintptr) uintptr {
	switch message {
	case _WM_TRAYNOTIFY:
		if uint32(lp) == _WM_RBUTTONUP {
			t.showMenu(hwnd)
		}
	case _WM_TRAY_UPDATE:
		n := int(wp)
		img := MakeTrayIcon(n)
		hIcon := makeHICON(img, trayLabel(n))
		old := t.curIcon.Swap(hIcon)
		nid := notifyIconData{
			cbSize: uint32(unsafe.Sizeof(notifyIconData{})),
			hWnd:   hwnd, uID: 1, uFlags: _NIF_ICON, hIcon: hIcon,
		}
		_shellNotifyIconW.Call(_NIM_MODIFY, uintptr(unsafe.Pointer(&nid)))
		if old != 0 {
			_destroyIcon.Call(old)
		}
	case _WM_TRAY_STOP:
		_postQuitMessage.Call(0)
	}
	r, _, _ := _defWindowProcW.Call(hwnd, uintptr(message), wp, lp)
	return r
}

func (t *windowsTrayIcon) showMenu(hwnd uintptr) {
	hMenu, _, _ := _createPopupMenu.Call()
	if hMenu == 0 {
		return
	}
	defer _destroyMenu.Call(hMenu)

	header, _ := windows.UTF16PtrFromString("Windows Navigator")
	exit, _ := windows.UTF16PtrFromString("Exit")
	_appendMenuW.Call(hMenu, _MF_STRING|_MF_GRAYED, 0, uintptr(unsafe.Pointer(header)))
	_appendMenuW.Call(hMenu, _MF_SEPARATOR, 0, 0)
	_appendMenuW.Call(hMenu, _MF_STRING, _IDM_EXIT, uintptr(unsafe.Pointer(exit)))

	type pt32 struct{ x, y int32 }
	var pt pt32
	_getCursorPos.Call(uintptr(unsafe.Pointer(&pt)))
	_setForegroundWindow.Call(hwnd)

	cmd, _, _ := _trackPopupMenu.Call(
		hMenu,
		_TPM_RIGHTALIGN|_TPM_BOTTOMALIGN|_TPM_NONOTIFY|_TPM_RETURNCMD,
		uintptr(pt.x), uintptr(pt.y),
		0, hwnd, 0,
	)
	if cmd == _IDM_EXIT {
		_postQuitMessage.Call(0)
		if t.onExit != nil {
			go t.onExit()
		}
	}
}

// NewTrayIcon returns a TrayIconBackend backed by Shell_NotifyIconW.
func NewTrayIcon(onExit func()) TrayIconBackend {
	return &windowsTrayIcon{onExit: onExit}
}
