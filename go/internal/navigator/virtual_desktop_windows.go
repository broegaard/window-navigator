//go:build windows

package navigator

import (
	"fmt"
	"runtime"
	"strconv"
	"sync"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

// ---------------------------------------------------------------------------
// Registry reader
// ---------------------------------------------------------------------------

const _vdRegKey = `SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops`

// DefaultRegistryDesktopReader returns a RegistryDesktopReader backed by the Windows registry.
func DefaultRegistryDesktopReader() RegistryDesktopReader {
	return func() (current []byte, all []byte, err error) {
		k, err := registry.OpenKey(registry.CURRENT_USER, _vdRegKey, registry.QUERY_VALUE)
		if err != nil {
			return nil, nil, fmt.Errorf("open registry key: %w", err)
		}
		defer k.Close()

		current, _, err = k.GetBinaryValue("CurrentVirtualDesktop")
		if err != nil {
			return nil, nil, fmt.Errorf("read CurrentVirtualDesktop: %w", err)
		}
		all, _, err = k.GetBinaryValue("VirtualDesktopIDs")
		if err != nil {
			return nil, nil, fmt.Errorf("read VirtualDesktopIDs: %w", err)
		}
		return current, all, nil
	}
}

// ---------------------------------------------------------------------------
// Public IVirtualDesktopManager via raw COM vtable
// ---------------------------------------------------------------------------

// IVirtualDesktopManager vtable indices (stable across all Windows versions)
const (
	_vtblIsWindowOnCurrentVirtualDesktop = 3
	_vtblGetWindowDesktopId              = 4
	_vtblMoveWindowToDesktop             = 5
)

var (
	_clsidVirtualDesktopManager = mustParseGUID("{AA509086-5CA9-4C25-8F95-589D3C07B48A}")
	_iidIVirtualDesktopManager  = mustParseGUID("{A5CD92FF-29BE-454C-8D04-D82879FB3F1B}")
)

// mustParseGUID panics if the GUID string is invalid — only called at init with literals.
func mustParseGUID(s string) windows.GUID {
	g, err := windows.GUIDFromString(s)
	if err != nil {
		panic(fmt.Sprintf("invalid GUID literal %q: %v", s, err))
	}
	return g
}

// rawVDManager wraps a raw IVirtualDesktopManager COM pointer.
type rawVDManager struct {
	ptr uintptr // IVirtualDesktopManager*
}

func (m *rawVDManager) IsWindowOnCurrentVirtualDesktop(hwnd uintptr) (bool, error) {
	var result int32
	hr, err := callNHR(
		vtableIndex(m.ptr, _vtblIsWindowOnCurrentVirtualDesktop),
		m.ptr,
		hwnd,
		uintptr(unsafe.Pointer(&result)),
	)
	if err != nil || hr != 0 {
		return false, fmt.Errorf("IsWindowOnCurrentVirtualDesktop HRESULT %#x: %w", hr, err)
	}
	return result != 0, nil
}

func (m *rawVDManager) GetWindowDesktopID(hwnd uintptr) (string, error) {
	var guid [16]byte
	hr, err := callNHR(
		vtableIndex(m.ptr, _vtblGetWindowDesktopId),
		m.ptr,
		hwnd,
		uintptr(unsafe.Pointer(&guid[0])),
	)
	if err != nil || hr != 0 {
		return "", fmt.Errorf("GetWindowDesktopId HRESULT %#x: %w", hr, err)
	}
	return GUIDToString(guid), nil
}

func (m *rawVDManager) MoveWindowToDesktop(hwnd uintptr, desktopGUID string) error {
	guid, err := StringToGUID(desktopGUID)
	if err != nil {
		return err
	}
	hr, err := callNHR(
		vtableIndex(m.ptr, _vtblMoveWindowToDesktop),
		m.ptr,
		hwnd,
		uintptr(unsafe.Pointer(&guid[0])),
	)
	if err != nil || hr != 0 {
		return fmt.Errorf("MoveWindowToDesktop HRESULT %#x: %w", hr, err)
	}
	return nil
}

// vtableIndex returns the function pointer at the given vtable index for a COM object ptr.
func vtableIndex(ptr uintptr, index uintptr) uintptr {
	vtbl := *(*uintptr)(unsafe.Pointer(ptr))
	return *(*uintptr)(unsafe.Pointer(vtbl + index*8))
}

// callNHR calls a Win32 function via SyscallN and returns (HRESULT, error).
func callNHR(fn uintptr, args ...uintptr) (uintptr, error) {
	r := callN(fn, args...)
	if r != 0 {
		return r, windows.Errno(r)
	}
	return 0, nil
}

// callN dispatches to the right SyscallN variant.
func callN(fn uintptr, args ...uintptr) uintptr {
	r, _, _ := syscall.SyscallN(fn, args...)
	return r
}

// ---------------------------------------------------------------------------
// Manager cache
// ---------------------------------------------------------------------------

type managerCache struct {
	once    sync.Once
	manager VirtualDesktopManager
}

func (c *managerCache) get() VirtualDesktopManager {
	c.once.Do(func() {
		var ptr uintptr
		const CLSCTX_INPROC_SERVER = 1
		ole32 := windows.NewLazySystemDLL("ole32.dll")
		coInitEx := ole32.NewProc("CoInitializeEx")
		coCreate := ole32.NewProc("CoCreateInstance")

		coInitEx.Call(0, 2) // COINIT_APARTMENTTHREADED

		hr, _, _ := coCreate.Call(
			uintptr(unsafe.Pointer(&_clsidVirtualDesktopManager)),
			0,
			CLSCTX_INPROC_SERVER,
			uintptr(unsafe.Pointer(&_iidIVirtualDesktopManager)),
			uintptr(unsafe.Pointer(&ptr)),
		)
		if hr != 0 || ptr == 0 {
			return
		}
		c.manager = &rawVDManager{ptr: ptr}
	})
	return c.manager
}

var _managerCache managerCache

// DefaultVirtualDesktopManager returns the lazily-initialized COM manager, or nil on failure.
func DefaultVirtualDesktopManager() VirtualDesktopManager {
	return _managerCache.get()
}

// ---------------------------------------------------------------------------
// IVirtualDesktopManagerInternal — pyvda equivalent (Win11 22H2+ cross-process moves)
// ---------------------------------------------------------------------------

// GUIDs for ImmersiveShell, IServiceProvider, IApplicationViewCollection.
var (
	_clsidImmersiveShell  = mustParseGUID("{C2F03A33-21F5-47FA-B4BB-156362A2F239}")
	_sidVDManagerInternal = mustParseGUID("{C5E0CDCA-7B6E-41B2-9FC4-D93975CC467B}")
	_iidServiceProvider   = mustParseGUID("{6D5140C1-7436-11CE-8034-00AA006009FA}")
	_iidAppViewCollection = mustParseGUID("{1841C6D7-4F9D-42C0-AF41-8747538F10E5}")

	// IVirtualDesktopManagerInternal IIDs — newest first for probing.
	_iidVDMI_26100 = mustParseGUID("{53F5CA0B-158F-4124-900C-057158060B27}")
	_iidVDMI_22631 = mustParseGUID("{4970BA3D-FD4E-4647-BEA3-D89076EF4B9C}")
	_iidVDMI_22621 = mustParseGUID("{A3175F2D-239C-4BD2-8AA0-EEBA8B0B138E}")
	_iidVDMI_21313 = mustParseGUID("{B2F925B9-5A0F-4D2E-9F4D-2B1507593C10}")
	_iidVDMI_20231 = mustParseGUID("{094AFE11-44F2-4BA0-976F-29A97E263EE0}")
	_iidVDMI_9000  = mustParseGUID("{F31574D6-B682-4CDC-BD56-1827860ABEC6}")

	// IVirtualDesktop IIDs — version-specific.
	_iidVD_22621 = mustParseGUID("{3F07F4BE-B107-441A-AF0F-39D82529072C}")
	_iidVD_21313 = mustParseGUID("{536D3495-B208-4CC9-AE26-DE8111275BF8}")
	_iidVD_20231 = mustParseGUID("{62FDF88B-11CA-4AFB-8BD8-2296DFAE49E2}")
	_iidVD_9000  = mustParseGUID("{FF72FFDD-BE7E-43FC-9C03-AD81681E88E4}")
)

var _allowSetForegroundWindowProc = windows.NewLazySystemDLL("user32.dll").NewProc("AllowSetForegroundWindow")

// vdInternalLayout holds version-specific vtable indices for IVirtualDesktopManagerInternal.
// hwndParam: older builds (20231–22449) pass HWND=0 as first arg to GetCurrentDesktop,
// GetDesktops, and SwitchDesktop.
type vdInternalLayout struct {
	iidInternal    windows.GUID
	iidDesktop     windows.GUID
	idxMoveView    uintptr // MoveViewToDesktop(IApplicationView*, IVirtualDesktop*)
	idxGetCurrent  uintptr // GetCurrentDesktop([HWND,] IVirtualDesktop**)
	idxGetDesktops uintptr // GetDesktops([HWND,] IObjectArray**)
	idxSwitch      uintptr // SwitchDesktop([HWND,] IVirtualDesktop*)
	hwndParam      bool
}

// _vdLayouts lists all known layouts in probe order (newest IID first).
// The 21313 IID is shared with build 22449, which has different indices; see _layout22449.
var _vdLayouts = []vdInternalLayout{
	{_iidVDMI_26100, _iidVD_22621, 4, 6, 7, 9, false},
	{_iidVDMI_22631, _iidVD_22621, 4, 6, 7, 9, false},
	{_iidVDMI_22621, _iidVD_22621, 4, 6, 7, 9, false},
	{_iidVDMI_21313, _iidVD_21313, 4, 6, 7, 9, true}, // build 21313–22448; 22449+ below
	{_iidVDMI_20231, _iidVD_20231, 4, 6, 7, 9, true},
	{_iidVDMI_9000, _iidVD_9000, 4, 6, 7, 9, false},
}

// _layout22449 uses the 21313 IID but GetAllCurrentDesktops was inserted at index 7,
// shifting GetDesktops to 8 and SwitchDesktop to 10.
var _layout22449 = vdInternalLayout{_iidVDMI_21313, _iidVD_21313, 4, 6, 8, 10, true}

// comRelease calls IUnknown::Release (vtable index 2) on ptr.
func comRelease(ptr uintptr) {
	if ptr == 0 {
		return
	}
	syscall.SyscallN(vtableIndex(ptr, 2), ptr)
}

// comQueryService calls IServiceProvider::QueryService (vtable index 3).
func comQueryService(sp uintptr, sid, riid *windows.GUID, ppv *uintptr) uintptr {
	r, _, _ := syscall.SyscallN(vtableIndex(sp, 3),
		sp,
		uintptr(unsafe.Pointer(sid)),
		uintptr(unsafe.Pointer(riid)),
		uintptr(unsafe.Pointer(ppv)),
	)
	return r
}

// getWindowsBuildNumber reads CurrentBuildNumber from HKLM.
func getWindowsBuildNumber() int {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`SOFTWARE\Microsoft\Windows NT\CurrentVersion`, registry.QUERY_VALUE)
	if err != nil {
		return 0
	}
	defer k.Close()
	s, _, err := k.GetStringValue("CurrentBuildNumber")
	if err != nil {
		return 0
	}
	n, _ := strconv.Atoi(s)
	return n
}

// vdInternal holds the initialized COM pointers and layout for one runtime session.
type vdInternal struct {
	vdmi   uintptr // IVirtualDesktopManagerInternal*
	avc    uintptr // IApplicationViewCollection*
	layout vdInternalLayout
}

func (m *vdInternal) getViewForHwnd(hwnd uintptr) (uintptr, error) {
	// IApplicationViewCollection::GetViewForHwnd is at vtable index 6.
	var view uintptr
	hr, _, _ := syscall.SyscallN(vtableIndex(m.avc, 6), m.avc, hwnd, uintptr(unsafe.Pointer(&view)))
	if hr != 0 || view == 0 {
		return 0, fmt.Errorf("GetViewForHwnd HRESULT %#x", hr)
	}
	return view, nil
}

func (m *vdInternal) getCurrentDesktop() (uintptr, error) {
	var desktop uintptr
	fn := vtableIndex(m.vdmi, m.layout.idxGetCurrent)
	var hr uintptr
	if m.layout.hwndParam {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, 0, uintptr(unsafe.Pointer(&desktop)))
	} else {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, uintptr(unsafe.Pointer(&desktop)))
	}
	if hr != 0 || desktop == 0 {
		return 0, fmt.Errorf("GetCurrentDesktop HRESULT %#x", hr)
	}
	return desktop, nil
}

func (m *vdInternal) getNthDesktop(n int) (uintptr, error) {
	var arr uintptr
	fn := vtableIndex(m.vdmi, m.layout.idxGetDesktops)
	var hr uintptr
	if m.layout.hwndParam {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, 0, uintptr(unsafe.Pointer(&arr)))
	} else {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, uintptr(unsafe.Pointer(&arr)))
	}
	if hr != 0 || arr == 0 {
		return 0, fmt.Errorf("GetDesktops HRESULT %#x", hr)
	}
	defer comRelease(arr)

	// IObjectArray::GetCount at vtable index 3.
	var count uint32
	syscall.SyscallN(vtableIndex(arr, 3), arr, uintptr(unsafe.Pointer(&count)))
	if n < 1 || n > int(count) {
		return 0, fmt.Errorf("desktop %d out of range 1..%d", n, count)
	}

	// IObjectArray::GetAt(n-1, &IID_IVirtualDesktop, &desktop) at vtable index 4.
	iid := m.layout.iidDesktop
	var desktop uintptr
	hr, _, _ = syscall.SyscallN(vtableIndex(arr, 4), arr,
		uintptr(n-1),
		uintptr(unsafe.Pointer(&iid)),
		uintptr(unsafe.Pointer(&desktop)),
	)
	if hr != 0 || desktop == 0 {
		return 0, fmt.Errorf("IObjectArray::GetAt(%d) HRESULT %#x", n-1, hr)
	}
	return desktop, nil
}

func (m *vdInternal) moveViewToDesktop(view, desktop uintptr) error {
	hr, _, _ := syscall.SyscallN(vtableIndex(m.vdmi, m.layout.idxMoveView), m.vdmi, view, desktop)
	if hr != 0 {
		return fmt.Errorf("MoveViewToDesktop HRESULT %#x", hr)
	}
	return nil
}

func (m *vdInternal) switchDesktop(desktop uintptr) error {
	fn := vtableIndex(m.vdmi, m.layout.idxSwitch)
	var hr uintptr
	if m.layout.hwndParam {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, 0, desktop)
	} else {
		hr, _, _ = syscall.SyscallN(fn, m.vdmi, desktop)
	}
	if hr != 0 {
		return fmt.Errorf("SwitchDesktop HRESULT %#x", hr)
	}
	return nil
}

// probeVDInternal creates the ImmersiveShell service provider and probes for the correct
// IVirtualDesktopManagerInternal IID (newest first). Must be called from a goroutine that
// has called runtime.LockOSThread and CoInitializeEx(APARTMENTTHREADED).
func probeVDInternal() *vdInternal {
	const clsctxLocalServer = 4

	ole32 := windows.NewLazySystemDLL("ole32.dll")
	ole32.NewProc("CoInitializeEx").Call(0, 2) // COINIT_APARTMENTTHREADED

	var pServiceProvider uintptr
	hr, _, _ := ole32.NewProc("CoCreateInstance").Call(
		uintptr(unsafe.Pointer(&_clsidImmersiveShell)),
		0,
		clsctxLocalServer,
		uintptr(unsafe.Pointer(&_iidServiceProvider)),
		uintptr(unsafe.Pointer(&pServiceProvider)),
	)
	if hr != 0 || pServiceProvider == 0 {
		return nil
	}
	// pServiceProvider is kept alive for the process lifetime.

	sidAVC := _iidAppViewCollection // SID == IID for IApplicationViewCollection
	var pAVC uintptr
	if comQueryService(pServiceProvider, &sidAVC, &_iidAppViewCollection, &pAVC) != 0 || pAVC == 0 {
		comRelease(pServiceProvider)
		return nil
	}

	buildNum := getWindowsBuildNumber()

	for _, layout := range _vdLayouts {
		iid := layout.iidInternal
		var pVDMI uintptr
		if comQueryService(pServiceProvider, &_sidVDManagerInternal, &iid, &pVDMI) != 0 || pVDMI == 0 {
			continue
		}
		// Build 22449+ shares the 21313 IID but has a different vtable layout.
		if layout.iidInternal == _iidVDMI_21313 && buildNum >= 22449 {
			layout = _layout22449
		}
		return &vdInternal{vdmi: pVDMI, avc: pAVC, layout: layout}
	}

	comRelease(pAVC)
	comRelease(pServiceProvider)
	return nil
}

// ---------------------------------------------------------------------------
// Worker goroutine — all internal COM calls run on a single locked OS thread.
// ---------------------------------------------------------------------------

type _internalOp int

const (
	_opMoveToCurrent _internalOp = iota
	_opMoveTo
	_opSwitchTo
)

type _internalReq struct {
	op   _internalOp
	hwnd uintptr
	n    int
	resp chan<- error
}

var _internalWorker struct {
	once sync.Once
	ch   chan _internalReq
}

func ensureInternalWorker() chan _internalReq {
	_internalWorker.once.Do(func() {
		ch := make(chan _internalReq, 1)
		_internalWorker.ch = ch
		go internalWorkerLoop(ch)
	})
	return _internalWorker.ch
}

func internalWorkerLoop(ch <-chan _internalReq) {
	runtime.LockOSThread()
	mgr := probeVDInternal()
	for req := range ch {
		var err error
		if mgr == nil {
			err = fmt.Errorf("IVirtualDesktopManagerInternal: not available on this system")
		} else {
			switch req.op {
			case _opMoveToCurrent:
				err = doMoveToCurrent(mgr, req.hwnd)
			case _opMoveTo:
				err = doMoveTo(mgr, req.hwnd, req.n)
			case _opSwitchTo:
				err = doSwitchTo(mgr, req.n)
			}
		}
		req.resp <- err
	}
}

func internalSend(op _internalOp, hwnd uintptr, n int) error {
	resp := make(chan error, 1)
	ensureInternalWorker() <- _internalReq{op: op, hwnd: hwnd, n: n, resp: resp}
	return <-resp
}

func doMoveToCurrent(m *vdInternal, hwnd uintptr) error {
	view, err := m.getViewForHwnd(hwnd)
	if err != nil {
		return err
	}
	defer comRelease(view)
	desktop, err := m.getCurrentDesktop()
	if err != nil {
		return err
	}
	defer comRelease(desktop)
	return m.moveViewToDesktop(view, desktop)
}

func doMoveTo(m *vdInternal, hwnd uintptr, n int) error {
	view, err := m.getViewForHwnd(hwnd)
	if err != nil {
		return err
	}
	defer comRelease(view)
	desktop, err := m.getNthDesktop(n)
	if err != nil {
		return err
	}
	defer comRelease(desktop)
	return m.moveViewToDesktop(view, desktop)
}

func doSwitchTo(m *vdInternal, n int) error {
	desktop, err := m.getNthDesktop(n)
	if err != nil {
		return err
	}
	defer comRelease(desktop)
	_allowSetForegroundWindowProc.Call(0xFFFFFFFF) // ASFW_ANY = -1
	return m.switchDesktop(desktop)
}

// ---------------------------------------------------------------------------
// DesktopSwitcher implementation
// ---------------------------------------------------------------------------

type windowsDesktopSwitcher struct{}

func (windowsDesktopSwitcher) MoveWindowToCurrent(hwnd uintptr) error {
	return internalSend(_opMoveToCurrent, hwnd, 0)
}

func (windowsDesktopSwitcher) MoveWindowTo(hwnd uintptr, n int) error {
	return internalSend(_opMoveTo, hwnd, n)
}

func (windowsDesktopSwitcher) SwitchTo(n int) error {
	return internalSend(_opSwitchTo, 0, n)
}

// DefaultDesktopSwitcher returns the Windows DesktopSwitcher.
func DefaultDesktopSwitcher() DesktopSwitcher {
	return windowsDesktopSwitcher{}
}
