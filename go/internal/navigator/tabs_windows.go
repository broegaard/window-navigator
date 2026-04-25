//go:build windows

package navigator

import (
	"unsafe"

	"golang.org/x/sys/windows"
)

// IUIAutomation vtable indices (IUnknown = 0–2; stable across all Windows versions).
const (
	_vtblUiaElementFromHandle  = uintptr(6)
	_vtblUiaCreateTrueCondition = uintptr(29)

	_vtblElemFindAll                = uintptr(6)
	_vtblElemGetCurrentPropertyValue = uintptr(10)
	_vtblElemGetCurrentPattern      = uintptr(14)

	_vtblArrLength     = uintptr(3)
	_vtblArrGetElement = uintptr(4)

	_vtblSelItemSelect = uintptr(3)
)

var (
	_clsidCUIAutomation = mustParseGUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")
	_iidIUIAutomation   = mustParseGUID("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}")

	_iidIUIAutomationSelectionItemPattern = mustParseGUID("{A8EFA66A-0FDA-421A-9194-38021F3578EA}")
	_iidIUIAutomationElementArray         = mustParseGUID("{14314595-B4BC-4055-95F2-58F2E42C9855}")

	_oleaut32      = windows.NewLazySystemDLL("oleaut32.dll")
	_variantClear  = _oleaut32.NewProc("VariantClear")
	_coCreateInst  = windows.NewLazySystemDLL("ole32.dll").NewProc("CoCreateInstance")
)

// uiaVariant is a 16-byte buffer matching the Windows VARIANT structure.
type uiaVariant [16]byte

const (
	_VT_I4   = uint16(3)
	_VT_BSTR = uint16(8)
)

func (v *uiaVariant) vt() uint16 { return *(*uint16)(unsafe.Pointer(&v[0])) }
func (v *uiaVariant) i4() int32  { return *(*int32)(unsafe.Pointer(&v[8])) }
func (v *uiaVariant) bstr() uintptr { return *(*uintptr)(unsafe.Pointer(&v[8])) }

// uiaRelease calls IUnknown::Release on ptr (vtable index 2). Safe to call with 0.
func uiaRelease(ptr uintptr) {
	if ptr == 0 {
		return
	}
	callN(vtableIndex(ptr, 2), ptr)
}

// createUIA creates an IUIAutomation COM object. Returns 0 on failure.
// CoInitializeEx must have been called on the current thread already.
func createUIA() uintptr {
	const clsctxInprocServer = uintptr(1)
	var ptr uintptr
	hr, _ := callNHR(
		_coCreateInst.Addr(),
		uintptr(unsafe.Pointer(&_clsidCUIAutomation)),
		0,
		clsctxInprocServer,
		uintptr(unsafe.Pointer(&_iidIUIAutomation)),
		uintptr(unsafe.Pointer(&ptr)),
	)
	if hr != 0 {
		return 0
	}
	return ptr
}

// uiaElementFromHandle calls IUIAutomation::ElementFromHandle.
func uiaElementFromHandle(uia uintptr, hwnd uintptr) uintptr {
	var elem uintptr
	hr, _ := callNHR(vtableIndex(uia, _vtblUiaElementFromHandle), uia, hwnd, uintptr(unsafe.Pointer(&elem)))
	if hr != 0 {
		return 0
	}
	return elem
}

// uiaCreateTrueCondition calls IUIAutomation::CreateTrueCondition.
func uiaCreateTrueCondition(uia uintptr) uintptr {
	var cond uintptr
	callNHR(vtableIndex(uia, _vtblUiaCreateTrueCondition), uia, uintptr(unsafe.Pointer(&cond))) //nolint
	return cond
}

// uiaGetChildren calls IUIAutomationElement::FindAll with TreeScope_Children.
// Caller owns the returned element pointers and must call uiaRelease on each.
func uiaGetChildren(elem uintptr, trueCond uintptr) []uintptr {
	var arr uintptr
	hr, _ := callNHR(
		vtableIndex(elem, _vtblElemFindAll),
		elem,
		UIATreeScopeChildren,
		trueCond,
		uintptr(unsafe.Pointer(&arr)),
	)
	if hr != 0 || arr == 0 {
		return nil
	}
	defer uiaRelease(arr)

	var length int32
	callNHR(vtableIndex(arr, _vtblArrLength), arr, uintptr(unsafe.Pointer(&length))) //nolint

	out := make([]uintptr, 0, length)
	for i := int32(0); i < length; i++ {
		var child uintptr
		callNHR(vtableIndex(arr, _vtblArrGetElement), arr, uintptr(i), uintptr(unsafe.Pointer(&child))) //nolint
		if child != 0 {
			out = append(out, child)
		}
	}
	return out
}

// uiaControlType returns UIAControlTypeProperty value for elem, or 0 on error.
func uiaControlType(elem uintptr) int {
	var v uiaVariant
	hr, _ := callNHR(vtableIndex(elem, _vtblElemGetCurrentPropertyValue), elem, UIAControlTypeProperty, uintptr(unsafe.Pointer(&v)))
	if hr != 0 || v.vt() != _VT_I4 {
		return 0
	}
	return int(v.i4())
}

// uiaName returns UIANameProperty as a Go string, releasing the BSTR.
func uiaName(elem uintptr) string {
	var v uiaVariant
	hr, _ := callNHR(vtableIndex(elem, _vtblElemGetCurrentPropertyValue), elem, UIANameProperty, uintptr(unsafe.Pointer(&v)))
	if hr != 0 || v.vt() != _VT_BSTR {
		return ""
	}
	bstr := v.bstr()
	var s string
	if bstr != 0 {
		s = windows.UTF16PtrToString((*uint16)(unsafe.Pointer(bstr)))
	}
	_variantClear.Call(uintptr(unsafe.Pointer(&v)))
	return s
}

// collectTabItems recursively walks the UIA tree under elem and returns tab-item elements.
// Stops at Document nodes (in-page ARIA widgets). Caller owns returned pointers.
func collectTabItems(elem uintptr, trueCond uintptr, depth int) []uintptr {
	if depth > 10 {
		return nil
	}
	ct := uiaControlType(elem)
	if ct == UIATabItemControlType {
		return []uintptr{elem}
	}
	if ct == UIADocumentControlType {
		return nil
	}
	children := uiaGetChildren(elem, trueCond)
	var items []uintptr
	for _, child := range children {
		sub := collectTabItems(child, trueCond, depth+1)
		if len(sub) > 0 && sub[0] != child {
			uiaRelease(child) // child not returned; release it
		}
		items = append(items, sub...)
	}
	return items
}

// fetchTabsWindows implements TabFetcher using IUIAutomation.
func fetchTabsWindows(hwnd uintptr) []TabInfo {
	uia := createUIA()
	if uia == 0 {
		return nil
	}
	defer uiaRelease(uia)

	root := uiaElementFromHandle(uia, hwnd)
	if root == 0 {
		return nil
	}
	defer uiaRelease(root)

	cond := uiaCreateTrueCondition(uia)
	defer uiaRelease(cond)

	items := collectTabItems(root, cond, 0)
	tabs := make([]TabInfo, 0, len(items))
	for idx, el := range items {
		name := uiaName(el)
		uiaRelease(el)
		tabs = append(tabs, TabInfo{Name: name, HWND: hwnd, Index: idx})
	}
	return tabs
}

// selectTabWindows implements TabSelector using IUIAutomation.
// Re-fetches the element at tab.Index to avoid cross-thread COM marshaling.
func selectTabWindows(tab TabInfo) {
	uia := createUIA()
	if uia == 0 {
		return
	}
	defer uiaRelease(uia)

	root := uiaElementFromHandle(uia, tab.HWND)
	if root == 0 {
		return
	}
	defer uiaRelease(root)

	cond := uiaCreateTrueCondition(uia)
	defer uiaRelease(cond)

	items := collectTabItems(root, cond, 0)
	defer func() {
		for _, el := range items {
			uiaRelease(el)
		}
	}()

	if tab.Index >= len(items) {
		return
	}
	target := items[tab.Index]

	// GetCurrentPattern → QueryInterface → IUIAutomationSelectionItemPattern::Select
	var patternUnknown uintptr
	callNHR(vtableIndex(target, _vtblElemGetCurrentPattern), target, UIASelectionItemPattern, uintptr(unsafe.Pointer(&patternUnknown))) //nolint
	if patternUnknown == 0 {
		return
	}
	defer uiaRelease(patternUnknown)

	// QueryInterface for IUIAutomationSelectionItemPattern
	var selPattern uintptr
	callNHR(vtableIndex(patternUnknown, 0), patternUnknown,
		uintptr(unsafe.Pointer(&_iidIUIAutomationSelectionItemPattern)),
		uintptr(unsafe.Pointer(&selPattern)),
	) //nolint
	if selPattern == 0 {
		return
	}
	defer uiaRelease(selPattern)

	callN(vtableIndex(selPattern, _vtblSelItemSelect), selPattern)
}

func init() {
	DefaultTabFetcher = fetchTabsWindows
	DefaultTabSelector = selectTabWindows
}
