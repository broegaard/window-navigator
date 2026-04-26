//go:build windows

package navigator

import (
	"image"
	"math"
	"runtime"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

// ---------------------------------------------------------------------------
// Win32 proc declarations (overlay-specific; not already in other _windows files)
// ---------------------------------------------------------------------------

var (
	_setWindowPos      = _user32.NewProc("SetWindowPos")
	_invalidateRect    = _user32.NewProc("InvalidateRect")
	_getClientRect     = _user32.NewProc("GetClientRect")
	_moveWindow        = _user32.NewProc("MoveWindow")
	_setWindowLongPtrW = _user32.NewProc("SetWindowLongPtrW")
	_getWindowLongPtrW = _user32.NewProc("GetWindowLongPtrW")
	_callWindowProcW   = _user32.NewProc("CallWindowProcW")
	_setFocusW         = _user32.NewProc("SetFocus")
	_beginPaint        = _user32.NewProc("BeginPaint")
	_endPaint          = _user32.NewProc("EndPaint")
	_fillRectW         = _user32.NewProc("FillRect")
	_loadCursorW       = _user32.NewProc("LoadCursorW")
	_setTimerW         = _user32.NewProc("SetTimer")
	_killTimerW        = _user32.NewProc("KillTimer")
	_setCursorPos      = _user32.NewProc("SetCursorPos")
	_getKeyStateW      = _user32.NewProc("GetKeyState")
	_postThreadMsg     = _user32.NewProc("PostThreadMessageW")
	_setWindowTextW    = _user32.NewProc("SetWindowTextW")

	_createCompatBmp  = _gdi32.NewProc("CreateCompatibleBitmap")
	_bitBlt           = _gdi32.NewProc("BitBlt")
	_createSolidBrush = _gdi32.NewProc("CreateSolidBrush")
	_setBkColorW      = _gdi32.NewProc("SetBkColor")

	_msimg32          = windows.NewLazySystemDLL("msimg32.dll")
	_alphaBlend       = _msimg32.NewProc("AlphaBlend")
	_getDpiForSystem  = _user32.NewProc("GetDpiForSystem")
)

// ---------------------------------------------------------------------------
// Constants (overlay-specific; not duplicating existing constants)
// ---------------------------------------------------------------------------

const (
	// Window messages
	_WM_SETFONT       = uint32(0x0030)
	_WM_ACTIVATE      = uint32(0x0006)
	_WM_PAINT         = uint32(0x000F)
	_WM_KEYDOWN       = uint32(0x0100)
	_WM_CHAR          = uint32(0x0102)
	_WM_COMMAND       = uint32(0x0111)
	_WM_TIMER         = uint32(0x0113)
	_WM_LBUTTONDOWN   = uint32(0x0201)
	_WM_MOUSEWHEEL    = uint32(0x020A)
	_WM_CTLCOLOREDIT  = uint32(0x0133)
	_WM_GETDLGCODE    = uint32(0x0087)

	// Virtual keys
	_VK_UP      = uintptr(0x26)
	_VK_DOWN    = uintptr(0x28)
	_VK_PRIOR   = uintptr(0x21)
	_VK_NEXT    = uintptr(0x22)
	_VK_END     = uintptr(0x23)
	_VK_HOME    = uintptr(0x24)
	_VK_RETURN  = uintptr(0x0D)
	_VK_ESCAPE  = uintptr(0x1B)
	_VK_TAB     = uintptr(0x09)
	_VK_BACK    = uintptr(0x08)
	_VK_CTRL    = uintptr(0x11)
	_VK_SHIFT   = uintptr(0x10)
	_VK_OEMMINUS = uintptr(0xBD)
	_VK_OEMPLUS  = uintptr(0xBB) // = key (unshifted)
	_VK_OEM5     = uintptr(0xDC) // ` key (US layout)

	// Edit control messages
	_EM_GETSEL     = uint32(0x00B0)
	_EM_SETSEL     = uint32(0x00B1)
	_EM_REPLACESEL = uint32(0x00C2)

	// Edit notifications
	_EN_CHANGE = uintptr(0x0300)

	// Edit control ID
	_editCtlID = uintptr(1001)

	// Window styles
	_WS_POPUP        = uintptr(0x80000000)
	_WS_CHILD        = uintptr(0x40000000)
	_WS_VISIBLE_STYLE = uintptr(0x10000000)
	_ES_LEFT         = uintptr(0x0000)
	_ES_AUTOHSCROLL  = uintptr(0x0080)
	_WS_EX_TOPMOST_  = uintptr(0x00000008)

	// SetWindowPos flags
	_SWP_NOMOVE     = uintptr(0x0002)
	_SWP_NOSIZE     = uintptr(0x0001)
	_SWP_NOZORDER   = uintptr(0x0004)
	_SWP_SHOWWINDOW = uintptr(0x0040)
	_SWP_HIDEWINDOW = uintptr(0x0080)
	_SWP_NOACTIVATE = uintptr(0x0010)
	_HWND_TOPMOST_  = ^uintptr(0) // (HWND)-1

	// ShowWindow
	_SW_SHOW_WINDOW = uintptr(5)
	_SW_HIDE_WINDOW = uintptr(0)

	// GDI
	_SRCCOPY = uintptr(0x00CC0020)

	// AlphaBlend BLENDFUNCTION: {AC_SRC_OVER, 0, 255, AC_SRC_ALPHA}
	_blendAlpha = uintptr(0x01FF0000)

	// GWLP
	_GWLP_WNDPROC_  = ^uintptr(3)  // -4
	_GWLP_USERDATA_ = ^uintptr(20) // -21

	// DrawText flags (overlay-specific)
	_DT_LEFT_          = uintptr(0x0000)
	_DT_NOPREFIX_      = uintptr(0x0800)
	_DT_END_ELLIPSIS_  = uintptr(0x8000)

	// Timer IDs
	_TIMER_PENDING_HIDE = uintptr(1)
	_TIMER_GRAB_FOCUS   = uintptr(2)

	// Custom WM_APP overlay messages (WM_APP = 0x8000)
	_WM_OVL_SHOW = uint32(0x8000 + 11)
	_WM_OVL_HIDE = uint32(0x8000 + 12)
	_WM_OVL_TABS = uint32(0x8000 + 13)
	_WM_OVL_ICON = uint32(0x8000 + 14)

	// DLGC flags
	_DLGC_WANTALLKEYS = uintptr(4)
	_DLGC_WANTCHARS   = uintptr(128)
	_DLGC_WANTTAB     = uintptr(2)
	_DLGC_HASSETSEL   = uintptr(8)
	_DLGC_WANTARROWS  = uintptr(1)
)

// ---------------------------------------------------------------------------
// Layout variables — defaults at 96 DPI, recomputed by scaleDPI() in loop()
// ---------------------------------------------------------------------------

const (
	_maxRows = 10 // dimensionless row count, not scaled
	_iconSz  = 32 // icon images are always 32×32 px, not scaled
)

var (
	_ovlW        = 1240
	_rowH        = 44
	_tabRowH     = 28
	_iconPX      = 8
	_iconPY      = 6  // (_rowH - _iconSz) / 2
	_badgeW      = 22
	_textX       = 68 // _iconPX + _iconSz + 2 + _badgeW + 4
	_titleY      = 7
	_procY       = 24
	_notifXOff   = 14
	_badgeEntSz  = 22
	_entFramePad = 8
	_entInnerPad = 4
	_entAreaH    = 56
	_arrowX      = 6
	_stripH      = 44 // _iconSz + 12
	_stripSlotW  = 44 // _iconSz + 12
	_stripPY     = 6  // (_stripH - _iconSz) / 2
	_stripPX     = 6  // (_stripSlotW - _iconSz) / 2
	_stripDivPad = 3
	_yEntry      = 1
	_yStrip      = 58  // _yEntry + _entAreaH + 1
	_yList       = 103 // _yStrip + _stripH + 1
	_editH       = 26

	// Font character heights in physical pixels at 96 DPI
	_fontTitleH = 13 // bold, ≈ 10pt
	_fontProcH  = 11 // regular, ≈ 8pt
	_fontEntryH = 17 // regular, ≈ 13pt
	_fontTabH   = 12 // regular, ≈ 9pt
)

// scaleDPI recomputes all pixel layout variables for a given DPI scale factor
// (monitorDPI / 96). Call once at overlay startup before creating any controls.
func scaleDPI(factor float64) {
	s := func(n int) int { return int(math.Round(float64(n) * factor)) }
	_ovlW        = s(1240)
	_rowH        = s(44)
	_tabRowH     = s(28)
	_iconPX      = s(8)
	_iconPY      = (_rowH - _iconSz) / 2
	_badgeW      = s(22)
	_textX       = _iconPX + _iconSz + 2 + _badgeW + 4
	_titleY      = s(7)
	_procY       = s(24)
	_notifXOff   = s(14)
	_badgeEntSz  = s(22)
	_entFramePad = s(8)
	_entInnerPad = s(4)
	_entAreaH    = s(56)
	_arrowX      = s(6)
	_stripH      = _iconSz + s(12)
	_stripSlotW  = _iconSz + s(12)
	_stripPY     = (_stripH - _iconSz) / 2
	_stripPX     = (_stripSlotW - _iconSz) / 2
	_stripDivPad = s(3)
	_yEntry      = 1
	_yStrip      = _yEntry + _entAreaH + 1
	_yList       = _yStrip + _stripH + 1
	_editH       = s(26)
	_fontTitleH  = s(13)
	_fontProcH   = s(11)
	_fontEntryH  = s(17)
	_fontTabH    = s(12)
}

// negH converts a positive pixel height to the negative lfHeight Win32 convention.
func negH(px int) uintptr { return ^uintptr(px - 1) }

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------

type ovlPalette struct {
	bg, rowBg, tabBg, rowSel uint32
	titleFg, procFg          uint32
	entryBg, entryFg         uint32
	border                   uint32
	notif                    uint32
}

func loadPalette() ovlPalette {
	dark := isDarkTheme()
	if dark {
		return ovlPalette{
			bg: 0x002E1E1E, rowBg: 0x002E1E1E, tabBg: 0x00382525, rowSel: 0x005B403D,
			titleFg: 0x00F4D6CD, procFg: 0x00C8ADA6,
			entryBg: 0x00443231, entryFg: 0x00F4D6CD,
			border: 0x005A4745, notif: 0x0025A8F9,
		}
	}
	return ovlPalette{
		bg: 0x00F5F5F5, rowBg: 0x00F5F5F5, tabBg: 0x00F2EBEB, rowSel: 0x00E7D0C8,
		titleFg: 0x002E1E1E, procFg: 0x00694F4C,
		entryBg: 0x00FFFFFF, entryFg: 0x002E1E1E,
		border: 0x00CCC0BC, notif: 0x0025A8F9,
	}
}

func isDarkTheme() bool {
	k, err := registry.OpenKey(registry.CURRENT_USER,
		`SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize`,
		registry.QUERY_VALUE)
	if err != nil {
		return true
	}
	defer k.Close()
	v, _, err := k.GetIntegerValue("AppsUseLightTheme")
	if err != nil {
		return true
	}
	return v == 0
}

// desktopColorRef converts a 1-based desktop number to a Win32 COLORREF (0x00BBGGRR).
func desktopColorRef(n int) uint32 {
	c := DesktopColors[(n-1)%len(DesktopColors)]
	return uint32(c[2])<<16 | uint32(c[1])<<8 | uint32(c[0])
}

// ---------------------------------------------------------------------------
// Win32 struct types (overlay-specific)
// ---------------------------------------------------------------------------

type paintStruct struct {
	hdc         uintptr
	fErase      int32
	rcPaint     Rect
	fRestore    int32
	fIncUpdate  int32
	rgbReserved [32]byte
}

// ---------------------------------------------------------------------------
// Overlay struct and constructor
// ---------------------------------------------------------------------------

type overlayShowArgs struct {
	windows        []WindowInfo
	initialDesktop int
}

type win32Overlay struct {
	cb       OverlayCallbacks
	hwnd     uintptr
	hwndEdit uintptr
	initDone chan struct{}

	mu          sync.Mutex
	pendingShow *overlayShowArgs
	pendingTabs map[uintptr][]TabInfo

	// Loop-thread-only state
	ctrl        *Controller
	visible     bool
	closing     bool
	pendingHide bool
	desktopNums []int

	scrollY int // pixel scroll offset into the list

	colors ovlPalette

	// Fonts (HFONT) — created in loop, freed in loop
	fontTitle uintptr // 10pt bold
	fontProc  uintptr // 8pt regular
	fontEntry uintptr // 13pt regular
	fontTab   uintptr // 9pt regular

	// Entry background brush (reused; freed in loop)
	entryBrush uintptr

	// Icon HBITMAPs per hwnd (DIBSection; freed on hide)
	iconBitmaps map[uintptr]uintptr

	// Icon images from background goroutine (mutex-protected)
	iconsMu  sync.Mutex
	iconImgs map[uintptr]*image.RGBA

	// Stable callback pointers (keep alive to prevent GC)
	mainCB uintptr
	editCB uintptr
	oldEditProc uintptr
}

// NewOverlay creates the overlay window and its message-loop goroutine, then returns.
func NewOverlay(cb OverlayCallbacks) Overlay {
	o := &win32Overlay{
		cb:          cb,
		initDone:    make(chan struct{}),
		pendingTabs: make(map[uintptr][]TabInfo),
		iconBitmaps: make(map[uintptr]uintptr),
		iconImgs:    make(map[uintptr]*image.RGBA),
		colors:      loadPalette(),
	}
	go o.loop()
	<-o.initDone
	return o
}

// Show posts a show request to the overlay goroutine.
func (o *win32Overlay) Show(windows []WindowInfo, initialDesktop int) {
	o.mu.Lock()
	o.pendingShow = &overlayShowArgs{windows: windows, initialDesktop: initialDesktop}
	o.mu.Unlock()
	_postMessageW.Call(o.hwnd, uintptr(_WM_OVL_SHOW), 0, 0)
}

// Hide posts a hide request to the overlay goroutine.
func (o *win32Overlay) Hide() {
	_postMessageW.Call(o.hwnd, uintptr(_WM_OVL_HIDE), 0, 0)
}

// ---------------------------------------------------------------------------
// Message loop (dedicated OS thread)
// ---------------------------------------------------------------------------

func (o *win32Overlay) loop() {
	runtime.LockOSThread()

	dpi, _, _ := _getDpiForSystem.Call()
	if dpi == 0 {
		dpi = 96
	}
	scaleDPI(float64(dpi) / 96.0)

	hInst, _, _ := _getModuleHandleW.Call(0)
	cursor, _, _ := _loadCursorW.Call(0, 32512) // IDC_ARROW

	o.mainCB = windows.NewCallback(func(h windows.HWND, m uint32, wp, lp uintptr) uintptr {
		return o.wndProc(uintptr(h), m, wp, lp)
	})

	clsName, _ := windows.UTF16PtrFromString("WinNavOverlay")
	wcx := wndClassExW{
		cbSize:        uint32(unsafe.Sizeof(wndClassExW{})),
		lpfnWndProc:   o.mainCB,
		hInstance:     hInst,
		hCursor:       cursor,
		lpszClassName: clsName,
	}
	_registerClassExW.Call(uintptr(unsafe.Pointer(&wcx)))

	winTitle, _ := windows.UTF16PtrFromString("Windows Navigator")
	hwnd, _, _ := _createWindowExW.Call(
		_WS_EX_TOPMOST_|uintptr(_WS_EX_TOOLWINDOW),
		uintptr(unsafe.Pointer(clsName)),
		uintptr(unsafe.Pointer(winTitle)),
		_WS_POPUP,
		0, 0, uintptr(_ovlW), uintptr(_yList+_rowH+1),
		0, 0, hInst, 0,
	)
	o.hwnd = hwnd

	// Create fonts (heights already scaled by scaleDPI above)
	face, _ := windows.UTF16PtrFromString("Segoe UI")
	o.fontTitle, _, _ = _createFontW.Call(
		negH(_fontTitleH), 0, 0, 0, _FW_BOLD,
		0, 0, 0, 0, 0, 0, 0, 0,
		uintptr(unsafe.Pointer(face)),
	)
	o.fontProc, _, _ = _createFontW.Call(
		negH(_fontProcH), 0, 0, 0, 0,
		0, 0, 0, 0, 0, 0, 0, 0,
		uintptr(unsafe.Pointer(face)),
	)
	o.fontEntry, _, _ = _createFontW.Call(
		negH(_fontEntryH), 0, 0, 0, 0,
		0, 0, 0, 0, 0, 0, 0, 0,
		uintptr(unsafe.Pointer(face)),
	)
	o.fontTab, _, _ = _createFontW.Call(
		negH(_fontTabH), 0, 0, 0, 0,
		0, 0, 0, 0, 0, 0, 0, 0,
		uintptr(unsafe.Pointer(face)),
	)

	// Create Edit control (positioned below; will be MoveWindow'd on show)
	editCls, _ := windows.UTF16PtrFromString("EDIT")
	hwndEdit, _, _ := _createWindowExW.Call(
		0,
		uintptr(unsafe.Pointer(editCls)),
		0,
		_WS_CHILD|_WS_VISIBLE_STYLE|_ES_LEFT|_ES_AUTOHSCROLL,
		uintptr(_entFramePad+_entInnerPad),
		uintptr(_yEntry+(_entAreaH-_editH)/2),
		uintptr(_ovlW-2*(_entFramePad+_entInnerPad)),
		uintptr(_editH),
		hwnd,
		_editCtlID,
		hInst, 0,
	)
	o.hwndEdit = hwndEdit
	_sendMessage.Call(hwndEdit, uintptr(_WM_SETFONT), o.fontEntry, 1)

	// Subclass Edit to intercept navigation keys
	o.editCB = windows.NewCallback(func(h windows.HWND, m uint32, wp, lp uintptr) uintptr {
		return o.editWndProc(uintptr(h), m, wp, lp)
	})
	oldProc, _, _ := _setWindowLongPtrW.Call(hwndEdit, _GWLP_WNDPROC_, o.editCB)
	o.oldEditProc = oldProc

	close(o.initDone)

	var msg msgStruct
	for {
		r, _, _ := _getMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
		if r == 0 || r == ^uintptr(0) {
			break
		}
		_translateMessage.Call(uintptr(unsafe.Pointer(&msg)))
		_dispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}

	// Cleanup
	for _, hbm := range o.iconBitmaps {
		_deleteObject.Call(hbm)
	}
	if o.entryBrush != 0 {
		_deleteObject.Call(o.entryBrush)
	}
	for _, hf := range []uintptr{o.fontTitle, o.fontProc, o.fontEntry, o.fontTab} {
		if hf != 0 {
			_deleteObject.Call(hf)
		}
	}
	_destroyWindowProc.Call(hwnd)
	_unregisterClassW.Call(uintptr(unsafe.Pointer(clsName)), hInst)
}

// ---------------------------------------------------------------------------
// Main window procedure
// ---------------------------------------------------------------------------

func (o *win32Overlay) wndProc(hwnd uintptr, msg uint32, wp, lp uintptr) uintptr {
	switch msg {
	case _WM_PAINT:
		o.doPaint(hwnd)
		return 0

	case _WM_ACTIVATE:
		if wp&0xFFFF == 0 { // WA_INACTIVE
			if !o.closing && o.visible {
				if o.pendingHide {
					_killTimerW.Call(hwnd, _TIMER_PENDING_HIDE)
				}
				_setTimerW.Call(hwnd, _TIMER_PENDING_HIDE, 50, 0)
				o.pendingHide = true
			}
		} else {
			if o.pendingHide {
				_killTimerW.Call(hwnd, _TIMER_PENDING_HIDE)
				o.pendingHide = false
			}
		}

	case _WM_TIMER:
		switch wp {
		case _TIMER_PENDING_HIDE:
			_killTimerW.Call(hwnd, _TIMER_PENDING_HIDE)
			o.pendingHide = false
			o.handleHide()
		case _TIMER_GRAB_FOCUS:
			_killTimerW.Call(hwnd, _TIMER_GRAB_FOCUS)
			o.doGrabFocus()
		}

	case _WM_COMMAND:
		if (wp>>16)&0xFFFF == _EN_CHANGE && wp&0xFFFF == _editCtlID {
			o.onTextChanged()
		}

	case _WM_CTLCOLOREDIT:
		hdc := wp
		_setTextColor.Call(hdc, uintptr(o.colors.entryFg))
		_setBkColorW.Call(hdc, uintptr(o.colors.entryBg))
		if o.entryBrush == 0 {
			o.entryBrush, _, _ = _createSolidBrush.Call(uintptr(o.colors.entryBg))
		}
		return o.entryBrush

	case _WM_MOUSEWHEEL:
		delta := int16((wp >> 16) & 0xFFFF)
		o.onMouseWheel(int(delta))

	case _WM_LBUTTONDOWN:
		x := int(int16(lp & 0xFFFF))
		y := int(int16((lp >> 16) & 0xFFFF))
		o.onWindowClick(x, y)

	case _WM_OVL_SHOW:
		o.mu.Lock()
		args := o.pendingShow
		o.pendingShow = nil
		o.mu.Unlock()
		if args != nil {
			o.handleShow(args)
		}

	case _WM_OVL_HIDE:
		o.handleHide()

	case _WM_OVL_TABS:
		hwnd2 := wp
		o.mu.Lock()
		tabs := o.pendingTabs[hwnd2]
		delete(o.pendingTabs, hwnd2)
		o.mu.Unlock()
		if o.ctrl != nil && len(tabs) > 0 {
			o.ctrl.SetTabs(hwnd2, tabs)
			o.invalidate()
			o.repositionAndResize()
		}

	case _WM_OVL_ICON:
		hwnd2 := wp
		o.iconsMu.Lock()
		img := o.iconImgs[hwnd2]
		o.iconsMu.Unlock()
		if img != nil {
			if _, ok := o.iconBitmaps[hwnd2]; !ok {
				if hbm := rgbaToHBITMAP(img); hbm != 0 {
					o.iconBitmaps[hwnd2] = hbm
				}
			}
			o.invalidateList()
		}
	}

	r, _, _ := _defWindowProcW.Call(hwnd, uintptr(msg), wp, lp)
	return r
}

// ---------------------------------------------------------------------------
// Edit control subclass procedure
// ---------------------------------------------------------------------------

func (o *win32Overlay) editWndProc(hwnd uintptr, msg uint32, wp, lp uintptr) uintptr {
	switch msg {
	case _WM_GETDLGCODE:
		return _DLGC_WANTALLKEYS | _DLGC_WANTCHARS | _DLGC_WANTTAB | _DLGC_HASSETSEL | _DLGC_WANTARROWS

	case _WM_CHAR:
		ch := rune(wp)
		switch ch {
		case '\r', '\t', '\x1b', '\x7f': // Enter, Tab, Escape, DEL (Ctrl+Backspace) — already handled in WM_KEYDOWN
			return 0
		}

	case _WM_KEYDOWN:
		vk := wp
		ctrlR, _, _ := _getKeyStateW.Call(_VK_CTRL)
		ctrl := ctrlR&0x8000 != 0
		shiftR, _, _ := _getKeyStateW.Call(_VK_SHIFT)
		shift := shiftR&0x8000 != 0

		switch vk {
		case _VK_UP:
			if o.ctrl != nil {
				o.ctrl.MoveUp()
				o.scrollToSelection()
				o.invalidateList()
			}
			return 0
		case _VK_DOWN:
			if o.ctrl != nil {
				o.ctrl.MoveDown()
				o.scrollToSelection()
				o.invalidateList()
			}
			return 0
		case _VK_PRIOR:
			if o.ctrl != nil {
				o.ctrl.MovePageUp(_maxRows)
				o.scrollToSelection()
				o.invalidateList()
			}
			return 0
		case _VK_NEXT:
			if o.ctrl != nil {
				o.ctrl.MovePageDown(_maxRows)
				o.scrollToSelection()
				o.invalidateList()
			}
			return 0
		case _VK_HOME:
			if ctrl {
				if o.ctrl != nil {
					o.ctrl.MoveToFirst()
					o.scrollToSelection()
					o.invalidateList()
				}
				return 0
			}
		case _VK_END:
			if ctrl {
				if o.ctrl != nil {
					o.ctrl.MoveToLast()
					o.scrollToSelection()
					o.invalidateList()
				}
				return 0
			}
		case _VK_RETURN:
			if ctrl {
				o.moveAndActivateSelected()
			} else {
				o.activateSelected()
			}
			return 0
		case _VK_ESCAPE:
			o.handleEscape()
			return 0
		case _VK_TAB:
			if ctrl {
				if o.ctrl != nil {
					o.ctrl.ToggleAllExpansions()
					o.invalidate()
					o.repositionAndResize()
				}
			} else if shift {
				if o.ctrl != nil {
					o.ctrl.CycleAppFilter(-1)
					o.invalidate()
				}
			} else {
				if o.ctrl != nil {
					o.ctrl.CycleAppFilter(1)
					o.invalidate()
				}
			}
			return 0
		case _VK_BACK:
			if ctrl {
				o.ctrlBackspace()
				return 0
			}
			if o.caretAtStart() {
				if o.ctrl != nil && o.ctrl.BellFilter() {
					o.ctrl.ToggleBellFilter()
					o.repositionEdit()
					o.invalidate()
					o.repositionAndResize()
					return 0
				}
				if len(o.desktopNums) > 0 {
					o.setDesktopFilter(o.desktopNums[:len(o.desktopNums)-1])
					return 0
				}
			}
		}

		// Ctrl+digit: toggle desktop badge or jump (with Shift)
		if ctrl && vk >= 0x31 && vk <= 0x39 {
			num := int(vk - 0x30)
			if shift {
				o.jumpToDesktop(num)
			} else {
				o.toggleDesktopBadge(num)
			}
			return 0
		}

		// Ctrl+= or Ctrl++ (increment badge)
		if ctrl && (vk == _VK_OEMPLUS || vk == 0x6B) {
			if len(o.desktopNums) == 1 && o.desktopNums[0] < 9 {
				o.setDesktopFilter([]int{o.desktopNums[0] + 1})
			}
			return 0
		}
		// Ctrl+- (decrement badge)
		if ctrl && (vk == _VK_OEMMINUS || vk == 0x6D) {
			if len(o.desktopNums) == 1 && o.desktopNums[0] > 1 {
				o.setDesktopFilter([]int{o.desktopNums[0] - 1})
			}
			return 0
		}
		// Ctrl+` (bell filter)
		if ctrl && (vk == _VK_OEM5 || vk == 0xC0) {
			if o.ctrl != nil {
				o.ctrl.ToggleBellFilter()
				o.repositionEdit()
				o.invalidate()
				o.repositionAndResize()
			}
			return 0
		}
	}

	r, _, _ := _callWindowProcW.Call(o.oldEditProc, hwnd, uintptr(msg), wp, lp)
	return r
}

// ---------------------------------------------------------------------------
// Show / hide handlers (called on the loop goroutine)
// ---------------------------------------------------------------------------

func (o *win32Overlay) handleShow(args *overlayShowArgs) {
	if o.visible {
		// Already open: toggle tab expansion
		if o.ctrl != nil {
			o.ctrl.ToggleAllExpansions()
			o.invalidate()
			o.repositionAndResize()
		}
		_setFocusW.Call(o.hwndEdit)
		return
	}

	o.ctrl = NewController(args.windows)
	o.closing = false
	o.scrollY = 0
	o.desktopNums = nil

	// Free icon bitmaps from previous show
	for _, hbm := range o.iconBitmaps {
		_deleteObject.Call(hbm)
	}
	o.iconBitmaps = make(map[uintptr]uintptr)
	o.iconsMu.Lock()
	o.iconImgs = make(map[uintptr]*image.RGBA)
	o.iconsMu.Unlock()

	// Apply initial desktop filter
	if args.initialDesktop > 0 {
		o.desktopNums = []int{args.initialDesktop}
		o.ctrl.SetDesktopNums(map[int]struct{}{args.initialDesktop: {}})
	}

	// Reset Edit control
	_setWindowTextW.Call(o.hwndEdit, 0)
	o.repositionEdit()

	// Resize and position the overlay window
	o.repositionAndResize()
	o.positionWindow()

	// Show topmost
	_setWindowPos.Call(o.hwnd, _HWND_TOPMOST_, 0, 0, 0, 0,
		_SWP_NOMOVE|_SWP_NOSIZE|_SWP_SHOWWINDOW)

	o.visible = true
	o.invalidate()

	// Delayed focus grab (50 ms, like Python)
	_setTimerW.Call(o.hwnd, _TIMER_GRAB_FOCUS, 50, 0)

	// Tab fetch goroutine — must run on a locked OS thread with COM initialized.
	wins := args.windows
	go func() {
		runtime.LockOSThread()
		defer runtime.UnlockOSThread() // registered first, runs last — COM must uninit first
		ole32 := windows.NewLazySystemDLL("ole32.dll")
		ole32.NewProc("CoInitializeEx").Call(0, 0) // COINIT_MULTITHREADED
		defer ole32.NewProc("CoUninitialize").Call()

		DbgLog("tabFetch: fetching tabs for %d windows", len(wins))
		for _, w := range wins {
			tabs := DefaultTabFetcher(w.HWND)
			DbgLog("tabFetch: hwnd=%#x got %d tabs", w.HWND, len(tabs))
			if len(tabs) > 0 {
				o.mu.Lock()
				o.pendingTabs[w.HWND] = tabs
				o.mu.Unlock()
				_postMessageW.Call(o.hwnd, uintptr(_WM_OVL_TABS), w.HWND, 0)
			}
		}
		DbgLog("tabFetch: done")
	}()

	// Icon fetch goroutine
	go func() {
		for _, w := range wins {
			img := ExtractIcon(w.HWND)
			o.iconsMu.Lock()
			o.iconImgs[w.HWND] = img
			o.iconsMu.Unlock()
			_postMessageW.Call(o.hwnd, uintptr(_WM_OVL_ICON), w.HWND, 0)
		}
	}()
}

func (o *win32Overlay) handleHide() {
	if !o.visible {
		return
	}
	o.visible = false
	o.closing = false
	o.pendingHide = false
	_killTimerW.Call(o.hwnd, _TIMER_PENDING_HIDE)
	_killTimerW.Call(o.hwnd, _TIMER_GRAB_FOCUS)

	_setWindowPos.Call(o.hwnd, 0, 0, 0, 0, 0,
		_SWP_NOMOVE|_SWP_NOSIZE|_SWP_HIDEWINDOW|_SWP_NOZORDER|_SWP_NOACTIVATE)

	// Cursor nudge to prevent spinning cursor under hidden overlay area
	type pt32 struct{ x, y int32 }
	var pt pt32
	_getCursorPos.Call(uintptr(unsafe.Pointer(&pt)))
	_setCursorPos.Call(uintptr(pt.x+1), uintptr(pt.y))
	_setCursorPos.Call(uintptr(pt.x), uintptr(pt.y))

	// Free icon bitmaps
	for _, hbm := range o.iconBitmaps {
		_deleteObject.Call(hbm)
	}
	o.iconBitmaps = make(map[uintptr]uintptr)

	if o.entryBrush != 0 {
		_deleteObject.Call(o.entryBrush)
		o.entryBrush = 0
	}
}

func (o *win32Overlay) doGrabFocus() {
	ForceForeground(o.hwnd)
	_setFocusW.Call(o.hwndEdit)
}

// ---------------------------------------------------------------------------
// GDI rendering
// ---------------------------------------------------------------------------

func (o *win32Overlay) doPaint(hwnd uintptr) {
	var ps paintStruct
	hdc, _, _ := _beginPaint.Call(hwnd, uintptr(unsafe.Pointer(&ps)))
	defer _endPaint.Call(hwnd, uintptr(unsafe.Pointer(&ps)))

	var rc Rect
	_getClientRect.Call(hwnd, uintptr(unsafe.Pointer(&rc)))
	w := int(rc.Right)
	h := int(rc.Bottom)

	// Back buffer
	hdcMem, _, _ := _createCompatibleDC.Call(hdc)
	hbm, _, _ := _createCompatBmp.Call(hdc, uintptr(w), uintptr(h))
	old, _, _ := _selectObject.Call(hdcMem, hbm)
	defer func() {
		_selectObject.Call(hdcMem, old)
		_deleteObject.Call(hbm)
		_deleteDC.Call(hdcMem)
	}()

	// Fill border background
	fillRect(hdcMem, 0, 0, w, h, o.colors.border)

	o.paintEntry(hdcMem, w)
	o.paintStrip(hdcMem, w)
	o.paintList(hdcMem, w, h)

	_bitBlt.Call(hdc, 0, 0, uintptr(w), uintptr(h), hdcMem, 0, 0, _SRCCOPY)
}

func (o *win32Overlay) paintEntry(hdc uintptr, w int) {
	// Entry area background
	fillRect(hdc, 1, _yEntry, w-2, _entAreaH, o.colors.entryBg)

	// Desktop prefix badges
	bx := 1 + _entFramePad + _entInnerPad
	by := _yEntry + (_entAreaH-_badgeEntSz)/2
	for _, num := range o.desktopNums {
		color := desktopColorRef(num)
		fillRect(hdc, bx, by, _badgeEntSz, _badgeEntSz, color)
		drawCenteredText(hdc, o.fontTitle, bx, by, _badgeEntSz, _badgeEntSz, itoa(num), 0x00FFFFFF)
		bx += _badgeEntSz + 2
	}

	// Bell badge
	if o.ctrl != nil && o.ctrl.BellFilter() {
		fillRect(hdc, bx, by, _badgeEntSz, _badgeEntSz, o.colors.notif)
		drawCenteredText(hdc, o.fontTitle, bx, by, _badgeEntSz, _badgeEntSz, "🔔", 0x00FFFFFF)
	}
}

func (o *win32Overlay) paintStrip(hdc uintptr, w int) {
	if o.ctrl == nil {
		return
	}
	fillRect(hdc, 1, _yStrip, w-2, _stripH, o.colors.bg)
	icons := o.ctrl.AppIcons()
	selIdx := o.ctrl.AppFilterIndex()
	totalW := len(icons) * _stripSlotW
	if totalW < w-2 {
		totalW = w - 2
	}
	_ = totalW

	for i, wi := range icons {
		x0 := 1 + i*_stripSlotW
		x1 := x0 + _stripSlotW
		if x0 >= w-1 {
			break
		}
		if x1 > w-1 {
			x1 = w - 1
		}
		slotW := x1 - x0

		var slotBg uint32 = o.colors.bg
		if selIdx != nil && i == *selIdx {
			slotBg = o.colors.rowSel
		}
		fillRect(hdc, x0, _yStrip, slotW, _stripH, slotBg)

		if hbm, ok := o.iconBitmaps[wi.HWND]; ok {
			drawIcon(hdc, hbm, x0+_stripPX, _yStrip+_stripPY)
		} else {
			fillRect(hdc, x0+_stripPX, _yStrip+_stripPY, _iconSz, _iconSz, 0x00888888)
		}

		// Divider
		if i < len(icons)-1 {
			drawLine(hdc, x1, _yStrip+_stripDivPad, x1, _yStrip+_stripH-_stripDivPad, o.colors.border)
		}
	}
}

func (o *win32Overlay) paintList(hdc uintptr, w, totalH int) {
	if o.ctrl == nil {
		return
	}
	listH := totalH - _yList - 1
	if listH <= 0 {
		return
	}

	fillRect(hdc, 1, _yList, w-2, listH, o.colors.rowBg)

	flat := o.ctrl.FlatList()
	sel := o.ctrl.SelectionIndex()
	innerW := w - 2

	y := -o.scrollY
	for i, item := range flat {
		rh := flatItemHeight(item)
		rowTop := _yList + y
		rowBot := rowTop + rh

		if rowBot <= _yList {
			y += rh
			continue
		}
		if rowTop >= _yList+listH {
			break
		}

		// Clip row to list area
		paintY := rowTop
		if paintY < _yList {
			paintY = _yList
		}
		paintH := rowBot - paintY
		if paintY+paintH > _yList+listH {
			paintH = _yList + listH - paintY
		}
		if paintH <= 0 {
			y += rh
			continue
		}

		if item.Tab != nil {
			// Tab row
			var bg uint32 = o.colors.tabBg
			if i == sel {
				bg = o.colors.rowSel
			}
			fillRect(hdc, 1, rowTop, innerW, rh, bg)
			rc := Rect{int32(1 + _textX), int32(rowTop + rh/2 - 6), int32(1 + innerW - 8), int32(rowTop + rh/2 + 6)}
			drawTextEllipsis(hdc, o.fontTab, item.Tab.Name, o.colors.titleFg, rc)
		} else {
			wi := item.Window
			var bg uint32 = o.colors.rowBg
			if i == sel {
				bg = o.colors.rowSel
			}
			fillRect(hdc, 1, rowTop, innerW, rh, bg)

			// Icon (drawn before arrow so arrow appears on top)
			ix := 1 + _iconPX
			iy := rowTop + _iconPY
			if hbm, ok := o.iconBitmaps[wi.HWND]; ok {
				drawIcon(hdc, hbm, ix, iy)
			} else {
				fillRect(hdc, ix, iy, _iconSz, _iconSz, 0x00888888)
			}

			// Expand/collapse arrow (drawn after icon so it is visible)
			if o.ctrl.TabCount(wi.HWND) > 1 {
				arrow := "▸"
				if o.ctrl.IsExpanded(wi.HWND) {
					arrow = "▾"
				}
				rc := Rect{int32(1 + _arrowX), int32(rowTop + rh/2 - 8), int32(1 + _arrowX + 14), int32(rowTop + rh/2 + 8)}
				drawTextEllipsis(hdc, o.fontProc, arrow, o.colors.procFg, rc)
			}

			// Desktop badge
			if wi.DesktopNumber > 0 {
				bx := 1 + _iconPX + _iconSz + 2
				bByteY := rowTop + (rh-_badgeW)/2
				color := desktopColorRef(wi.DesktopNumber)
				fillRect(hdc, bx, bByteY, _badgeW, _badgeW, color)
				drawCenteredText(hdc, o.fontTitle, bx, bByteY, _badgeW, _badgeW, itoa(wi.DesktopNumber), 0x00FFFFFF)
			}

			// Title
			txLeft := int32(1 + _textX)
			titleRC := Rect{txLeft, int32(rowTop + _titleY), int32(1 + innerW - 8), int32(rowTop + _titleY + 18)}
			drawTextEllipsis(hdc, o.fontTitle, wi.Title, o.colors.titleFg, titleRC)

			// Process name
			procRC := Rect{txLeft, int32(rowTop + _procY), int32(1 + innerW - 8), int32(rowTop + _procY + 14)}
			drawTextEllipsis(hdc, o.fontProc, wi.ProcessName, o.colors.procFg, procRC)

			// Notification bell
			if wi.HasNotification {
				bxNotif := 1 + innerW - _notifXOff
				byNotif := rowTop + rh/2
				drawCenteredText(hdc, o.fontEntry, bxNotif-10, byNotif-10, 20, 20, "🔔", o.colors.notif)
			}
		}

		y += rh
	}
}

// ---------------------------------------------------------------------------
// GDI helpers
// ---------------------------------------------------------------------------

func fillRect(hdc uintptr, x, y, w, h int, color uint32) {
	if w <= 0 || h <= 0 {
		return
	}
	brush, _, _ := _createSolidBrush.Call(uintptr(color))
	rc := Rect{int32(x), int32(y), int32(x + w), int32(y + h)}
	_fillRectW.Call(hdc, uintptr(unsafe.Pointer(&rc)), brush)
	_deleteObject.Call(brush)
}

func drawCenteredText(hdc, hfont uintptr, x, y, w, h int, text string, color uint32) {
	rc := Rect{int32(x), int32(y), int32(x + w), int32(y + h)}
	old, _, _ := _selectObject.Call(hdc, hfont)
	_setTextColor.Call(hdc, uintptr(color))
	_setBkMode.Call(hdc, _TRANSPARENT)
	tw, _ := windows.UTF16PtrFromString(text)
	_drawTextW.Call(hdc, uintptr(unsafe.Pointer(tw)), ^uintptr(0),
		uintptr(unsafe.Pointer(&rc)),
		_DT_CENTER|_DT_VCENTER|_DT_SINGLELINE|_DT_NOPREFIX_)
	_selectObject.Call(hdc, old)
}

func drawTextEllipsis(hdc uintptr, hfont uintptr, text string, color uint32, rc Rect) {
	old, _, _ := _selectObject.Call(hdc, hfont)
	_setTextColor.Call(hdc, uintptr(color))
	_setBkMode.Call(hdc, _TRANSPARENT)
	tw, _ := windows.UTF16PtrFromString(text)
	_drawTextW.Call(hdc, uintptr(unsafe.Pointer(tw)), ^uintptr(0),
		uintptr(unsafe.Pointer(&rc)),
		_DT_LEFT_|_DT_NOPREFIX_|_DT_END_ELLIPSIS_|_DT_SINGLELINE|_DT_VCENTER)
	_selectObject.Call(hdc, old)
}

func drawIcon(hdc uintptr, hbm uintptr, x, y int) {
	hdcSrc, _, _ := _createCompatibleDC.Call(0)
	old, _, _ := _selectObject.Call(hdcSrc, hbm)
	_alphaBlend.Call(
		hdc, uintptr(x), uintptr(y), _iconSz, _iconSz,
		hdcSrc, 0, 0, _iconSz, _iconSz,
		_blendAlpha,
	)
	_selectObject.Call(hdcSrc, old)
	_deleteDC.Call(hdcSrc)
}

func drawLine(hdc uintptr, x1, y1, x2, y2 int, color uint32) {
	// Draw a 1px vertical or horizontal line via FillRect
	if x1 == x2 {
		fillRect(hdc, x1, y1, 1, y2-y1, color)
	} else {
		fillRect(hdc, x1, y1, x2-x1, 1, color)
	}
}

// rgbaToHBITMAP converts an *image.RGBA to a pre-multiplied-alpha HBITMAP suitable for AlphaBlend.
func rgbaToHBITMAP(img *image.RGBA) uintptr {
	w, h := img.Bounds().Dx(), img.Bounds().Dy()
	buf := make([]byte, w*h*4)
	for i := 0; i < w*h; i++ {
		r := img.Pix[i*4+0]
		g := img.Pix[i*4+1]
		b := img.Pix[i*4+2]
		a := img.Pix[i*4+3]
		buf[i*4+0] = byte(int(b) * int(a) / 255)
		buf[i*4+1] = byte(int(g) * int(a) / 255)
		buf[i*4+2] = byte(int(r) * int(a) / 255)
		buf[i*4+3] = a
	}
	bmih := bitmapInfoHeader{
		biSize:     uint32(unsafe.Sizeof(bitmapInfoHeader{})),
		biWidth:    int32(w),
		biHeight:   -int32(h),
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
	return hbm
}

// ---------------------------------------------------------------------------
// Action handlers
// ---------------------------------------------------------------------------

func (o *win32Overlay) activateSelected() {
	if o.ctrl == nil {
		o.handleHide()
		return
	}
	item := o.ctrl.SelectedItem()
	if item == nil {
		o.handleHide()
		return
	}
	o.closing = true
	if item.Tab != nil {
		DefaultTabSelector(*item.Tab)
	}
	o.cb.OnActivate(item.HWND())
	o.handleHide()
}

func (o *win32Overlay) moveAndActivateSelected() {
	if o.ctrl == nil {
		o.handleHide()
		return
	}
	hwnd := o.ctrl.SelectedHWND()
	if hwnd == nil {
		o.handleHide()
		return
	}
	o.closing = true
	o.cb.OnMove(*hwnd)
	o.handleHide()
}

func (o *win32Overlay) handleEscape() {
	if o.ctrl == nil {
		o.handleHide()
		return
	}
	if o.ctrl.BellFilter() {
		o.ctrl.ToggleBellFilter()
		o.repositionEdit()
		o.invalidate()
		o.repositionAndResize()
		return
	}
	if o.ctrl.AppFilter() != nil {
		o.ctrl.ClearAppFilter()
		o.invalidate()
		return
	}
	o.handleHide()
}

func (o *win32Overlay) onTextChanged() {
	if o.ctrl == nil {
		return
	}
	text := o.getEditText()
	if text != o.ctrl.Query() {
		o.ctrl.SetQuery(text)
		o.scrollToSelection()
		o.invalidate()
		o.repositionAndResize()
	}
}

func (o *win32Overlay) onMouseWheel(delta int) {
	if !o.visible || o.ctrl == nil {
		return
	}
	lines := delta / 120 // positive = up, negative = down (WHEEL_DELTA = 120)
	o.scrollY -= lines * _rowH
	o.clampScroll()
	o.invalidateList()
}

func (o *win32Overlay) onWindowClick(x, y int) {
	if o.ctrl == nil || !o.visible {
		return
	}
	// Icon strip click
	if y >= _yStrip && y < _yStrip+_stripH {
		icons := o.ctrl.AppIcons()
		slotIdx := (x - 1) / _stripSlotW
		if slotIdx >= 0 && slotIdx < len(icons) {
			selIdx := o.ctrl.AppFilterIndex()
			if selIdx != nil && *selIdx == slotIdx {
				o.ctrl.ClearAppFilter()
			} else {
				// Set filter to clicked app by name
				if slotIdx < len(icons) {
					name := icons[slotIdx].ProcessName
					o.ctrl.SetAppFilterByName(name)
				}
			}
			o.invalidate()
		}
		return
	}
	// List click
	if y >= _yList {
		clickY := y - _yList + o.scrollY
		cy := 0
		for i, item := range o.ctrl.FlatList() {
			rh := flatItemHeight(item)
			if clickY >= cy && clickY < cy+rh {
				o.ctrl.SetSelectionIndex(i)
				// Click in the arrow area of a window row with tabs: toggle expansion.
				if item.Window != nil && x < 1+_iconPX+_iconSz/2 && o.ctrl.TabCount(item.Window.HWND) > 1 {
					o.ctrl.ToggleExpansion(item.Window.HWND)
					o.invalidate()
					o.repositionAndResize()
				} else {
					o.activateSelected()
				}
				return
			}
			cy += rh
		}
	}
}

func (o *win32Overlay) toggleDesktopBadge(num int) {
	nums := make([]int, 0, len(o.desktopNums)+1)
	found := false
	for _, n := range o.desktopNums {
		if n == num {
			found = true
		} else {
			nums = append(nums, n)
		}
	}
	if !found {
		nums = append(nums, num)
	}
	o.setDesktopFilter(nums)
}

func (o *win32Overlay) setDesktopFilter(nums []int) {
	o.desktopNums = nums
	o.repositionEdit()
	if o.ctrl != nil {
		set := make(map[int]struct{}, len(nums))
		for _, n := range nums {
			set[n] = struct{}{}
		}
		o.ctrl.SetDesktopNums(set)
	}
	o.scrollY = 0
	o.invalidate()
	o.repositionAndResize()
}

func (o *win32Overlay) jumpToDesktop(num int) {
	o.setDesktopFilter([]int{num})
	if o.ctrl != nil && len(o.ctrl.FlatList()) > 0 {
		o.activateSelected()
	} else {
		SwitchToDesktopNumber(num, DefaultDesktopSwitcher())
		o.handleHide()
	}
}

func (o *win32Overlay) ctrlBackspace() {
	text := o.getEditText()
	r, _, _ := _sendMessage.Call(o.hwndEdit, uintptr(_EM_GETSEL), 0, 0)
	cursor := int(r & 0xFFFF)
	pos := cursor
	for pos > 0 && text[pos-1] == ' ' {
		pos--
	}
	for pos > 0 && text[pos-1] != ' ' {
		pos--
	}
	if pos < cursor {
		_sendMessage.Call(o.hwndEdit, uintptr(_EM_SETSEL), uintptr(pos), uintptr(cursor))
		empty, _ := windows.UTF16PtrFromString("")
		_sendMessage.Call(o.hwndEdit, uintptr(_EM_REPLACESEL), 0, uintptr(unsafe.Pointer(empty)))
		o.onTextChanged()
	}
}

// ---------------------------------------------------------------------------
// Layout / geometry helpers
// ---------------------------------------------------------------------------

func (o *win32Overlay) repositionEdit() {
	badgeCount := len(o.desktopNums)
	if o.ctrl != nil && o.ctrl.BellFilter() {
		badgeCount++
	}
	ex := 1 + _entFramePad + _entInnerPad + badgeCount*(_badgeEntSz+2)
	ey := _yEntry + (_entAreaH-_editH)/2
	ew := _ovlW - ex - (_entFramePad + _entInnerPad) - 2
	if ew < 50 {
		ew = 50
	}
	_moveWindow.Call(o.hwndEdit, uintptr(ex), uintptr(ey), uintptr(ew), uintptr(_editH), 1)
}

func (o *win32Overlay) repositionAndResize() {
	if !o.visible || o.ctrl == nil {
		return
	}
	listH := o.currentListHeight()
	newH := _yList + listH + 1
	_setWindowPos.Call(o.hwnd, 0, 0, 0, uintptr(_ovlW), uintptr(newH),
		_SWP_NOMOVE|_SWP_NOZORDER|_SWP_NOACTIVATE)
}

func (o *win32Overlay) positionWindow() {
	left, top, right, bottom := GetCursorMonitorWorkArea()
	monW := right - left
	monH := bottom - top
	maxH := _yList + _maxRows*_rowH + 1
	x := left + (monW-_ovlW)/2
	y := top + (monH-maxH)/2
	listH := o.currentListHeight()
	curH := _yList + listH + 1
	_setWindowPos.Call(o.hwnd, 0, uintptr(x), uintptr(y), uintptr(_ovlW), uintptr(curH),
		_SWP_NOZORDER|_SWP_NOACTIVATE)
}

func (o *win32Overlay) currentListHeight() int {
	if o.ctrl == nil {
		return _rowH
	}
	flat := o.ctrl.FlatList()
	total := 0
	for _, item := range flat {
		total += flatItemHeight(item)
	}
	max := _maxRows * _rowH
	if total > max {
		total = max
	}
	if total < _rowH {
		total = _rowH
	}
	return total
}

func (o *win32Overlay) scrollToSelection() {
	if o.ctrl == nil {
		return
	}
	flat := o.ctrl.FlatList()
	sel := o.ctrl.SelectionIndex()
	if sel < 0 || sel >= len(flat) {
		return
	}
	selY := 0
	for i, item := range flat {
		if i == sel {
			break
		}
		selY += flatItemHeight(item)
	}
	selH := flatItemHeight(flat[sel])
	listH := o.currentListHeight()
	if selY < o.scrollY {
		o.scrollY = selY
	} else if selY+selH > o.scrollY+listH {
		o.scrollY = selY + selH - listH
	}
	o.clampScroll()
}

func (o *win32Overlay) clampScroll() {
	if o.ctrl == nil || o.scrollY < 0 {
		o.scrollY = 0
		return
	}
	total := 0
	for _, item := range o.ctrl.FlatList() {
		total += flatItemHeight(item)
	}
	maxScroll := total - o.currentListHeight()
	if maxScroll < 0 {
		maxScroll = 0
	}
	if o.scrollY > maxScroll {
		o.scrollY = maxScroll
	}
}

func (o *win32Overlay) invalidate() {
	_invalidateRect.Call(o.hwnd, 0, 1)
}

func (o *win32Overlay) invalidateList() {
	var rc Rect
	_getClientRect.Call(o.hwnd, uintptr(unsafe.Pointer(&rc)))
	listRC := Rect{0, int32(_yList), rc.Right, rc.Bottom}
	_invalidateRect.Call(o.hwnd, uintptr(unsafe.Pointer(&listRC)), 1)
}

func (o *win32Overlay) caretAtStart() bool {
	r, _, _ := _sendMessage.Call(o.hwndEdit, uintptr(_EM_GETSEL), 0, 0)
	return r&0xFFFF == 0
}

func (o *win32Overlay) getEditText() string {
	buf := make([]uint16, 512)
	n, _, _ := _getWindowText.Call(o.hwndEdit, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	return windows.UTF16ToString(buf[:n])
}

// ---------------------------------------------------------------------------
// Misc helpers
// ---------------------------------------------------------------------------

func flatItemHeight(item FlatItem) int {
	if item.Tab != nil {
		return _tabRowH
	}
	return _rowH
}

func itoa(n int) string {
	if n >= 0 && n <= 9 {
		return string(rune('0' + n))
	}
	return "?"
}

// SetSelectionIndex sets the selection index directly (used for click-to-activate).
func (c *Controller) SetSelectionIndex(i int) {
	if i >= 0 && i < len(c.FlatList()) {
		c.selectionIndex = i
	}
}

// SetAppFilterByName sets the app filter to the given process name.
func (c *Controller) SetAppFilterByName(name string) {
	c.appFilter = &name
	c.resetSelection()
}
