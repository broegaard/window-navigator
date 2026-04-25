//go:build windows

package navigator

import (
	"fmt"
	"sync"
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

func (m *rawVDManager) vtableCall(index uintptr, args ...uintptr) (uintptr, error) {
	// COM vtable: object → vtable_ptr → fn_ptrs
	vtblPtr := *(*uintptr)(unsafe.Pointer(m.ptr))
	fn := *(*uintptr)(unsafe.Pointer(vtblPtr + index*8))
	r, _, _ := windows.NewCallback(func() uintptr { return 0 }) // not used; call directly
	_ = r
	// Use syscall.SyscallN to call the vtable function.
	var result uintptr
	switch len(args) {
	case 1:
		result, _, _ = windows.NewLazySystemDLL("ole32.dll").NewProc("CoInitializeEx").Call() // placeholder
		_ = result
		// Actual call: fn(this, arg0)
		result = callN(fn, append([]uintptr{m.ptr}, args...)...)
	default:
		result = callN(fn, append([]uintptr{m.ptr}, args...)...)
	}
	_ = result
	return callNHR(fn, append([]uintptr{m.ptr}, args...)...)
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
	r, _, _ := windows.SyscallN(fn, args...)
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
// IVirtualDesktopManagerInternal (pyvda equivalent)
// ---------------------------------------------------------------------------

// windowsDesktopSwitcher implements DesktopSwitcher using IVirtualDesktopManagerInternal.
// The vtable layout is Windows-build-dependent; we detect the build number.
// For now, this uses the Windows 11 22H2+ layout (BuildNumber >= 22621).
// TODO: add version detection for earlier Windows 10/11 layouts.
type windowsDesktopSwitcher struct{}

func (windowsDesktopSwitcher) MoveWindowToCurrent(hwnd uintptr) error {
	return moveWindowToCurrentDesktopInternal(hwnd)
}

func (windowsDesktopSwitcher) MoveWindowTo(hwnd uintptr, n int) error {
	return moveWindowToDesktopNInternal(hwnd, n)
}

func (windowsDesktopSwitcher) SwitchTo(n int) error {
	return switchToDesktopNInternal(n)
}

// DefaultDesktopSwitcher returns the Windows DesktopSwitcher.
func DefaultDesktopSwitcher() DesktopSwitcher {
	return windowsDesktopSwitcher{}
}

// The IVirtualDesktopManagerInternal COM calls are version-specific.
// These stubs return errors until the version-specific implementation is added.
// When implemented, they will use IServiceProvider → IVirtualDesktopManagerInternal
// with vtable indices that vary by Windows build number.

func moveWindowToCurrentDesktopInternal(_ uintptr) error {
	return fmt.Errorf("IVirtualDesktopManagerInternal: not yet implemented")
}

func moveWindowToDesktopNInternal(_ uintptr, _ int) error {
	return fmt.Errorf("IVirtualDesktopManagerInternal: not yet implemented")
}

func switchToDesktopNInternal(_ int) error {
	return fmt.Errorf("IVirtualDesktopManagerInternal: not yet implemented")
}
