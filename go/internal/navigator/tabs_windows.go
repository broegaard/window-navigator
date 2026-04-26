//go:build windows

package navigator

import (
	"unsafe"

	"golang.org/x/sys/windows"
)

// IUIAutomation vtable indices (IUnknown = 0–2; stable across all Windows versions).
const (
	_vtblUiaElementFromHandle = uintptr(6)

	_vtblElemGetCurrentPropertyValue = uintptr(10)
	_vtblElemGetCurrentPattern       = uintptr(14)

	// IUIAutomation::get_RawViewWalker — returns an IUIAutomationTreeWalker that
	// visits every element without filtering. Used instead of FindAll because
	// FindAll requires IUIAutomationElementArray cross-process marshaling which
	// returns E_FAIL in MTA apartments on Windows 10/11.
	_vtblUiaRawViewWalker = uintptr(16)

	// IUIAutomationTreeWalker vtable indices
	_vtblWalkerFirstChild = uintptr(4) // GetFirstChildElement
	_vtblWalkerNextSib    = uintptr(6) // GetNextSiblingElement

	_vtblSelItemSelect = uintptr(3)
)

var (
	_clsidCUIAutomation = mustParseGUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")
	_iidIUIAutomation   = mustParseGUID("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}")

	_iidIUIAutomationSelectionItemPattern = mustParseGUID("{A8EFA66A-0FDA-421A-9194-38021F3578EA}")

	_oleaut32     = windows.NewLazySystemDLL("oleaut32.dll")
	_variantClear = _oleaut32.NewProc("VariantClear")
	_coCreateInst = windows.NewLazySystemDLL("ole32.dll").NewProc("CoCreateInstance")
)

// uiaVariant is a 16-byte buffer matching the Windows VARIANT structure.
type uiaVariant [16]byte

const (
	_VT_I4   = uint16(3)
	_VT_BSTR = uint16(8)
)

func (v *uiaVariant) vt() uint16      { return *(*uint16)(unsafe.Pointer(&v[0])) }
func (v *uiaVariant) i4() int32       { return *(*int32)(unsafe.Pointer(&v[8])) }
func (v *uiaVariant) bstr() uintptr   { return *(*uintptr)(unsafe.Pointer(&v[8])) }

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

// uiaRawViewWalker calls IUIAutomation::get_RawViewWalker.
func uiaRawViewWalker(uia uintptr) uintptr {
	var walker uintptr
	callNHR(vtableIndex(uia, _vtblUiaRawViewWalker), uia, uintptr(unsafe.Pointer(&walker))) //nolint
	return walker
}

// walkerFirstChild calls IUIAutomationTreeWalker::GetFirstChildElement.
func walkerFirstChild(walker, elem uintptr) uintptr {
	var child uintptr
	callNHR(vtableIndex(walker, _vtblWalkerFirstChild), walker, elem, uintptr(unsafe.Pointer(&child))) //nolint
	return child
}

// walkerNextSib calls IUIAutomationTreeWalker::GetNextSiblingElement.
func walkerNextSib(walker, elem uintptr) uintptr {
	var sib uintptr
	callNHR(vtableIndex(walker, _vtblWalkerNextSib), walker, elem, uintptr(unsafe.Pointer(&sib))) //nolint
	return sib
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

// collectTabItems recursively walks the UIA tree under elem using the RawViewWalker
// and returns tab-item elements. Stops at Document nodes (in-page ARIA widgets).
// Caller owns returned pointers.
func collectTabItems(elem uintptr, walker uintptr, depth int) []uintptr {
	DbgLog("collectTabItems: depth=%d elem=%#x", depth, elem)
	if depth > 10 {
		return nil
	}
	ct := uiaControlType(elem)
	DbgLog("collectTabItems: depth=%d controlType=%d", depth, ct)
	if ct == UIATabItemControlType {
		return []uintptr{elem}
	}
	if ct == UIADocumentControlType {
		return nil
	}

	var items []uintptr
	child := walkerFirstChild(walker, elem)
	DbgLog("collectTabItems: depth=%d firstChild=%#x", depth, child)
	for child != 0 {
		next := walkerNextSib(walker, child)
		sub := collectTabItems(child, walker, depth+1)
		if len(sub) == 0 || sub[0] != child {
			uiaRelease(child)
		}
		items = append(items, sub...)
		child = next
	}
	return items
}

// fetchTabsWindows implements TabFetcher using IUIAutomation.
func fetchTabsWindows(hwnd uintptr) []TabInfo {
	DbgLog("fetchTabs: %#x createUIA", hwnd)
	uia := createUIA()
	if uia == 0 {
		DbgLog("fetchTabs: %#x createUIA=0, skip", hwnd)
		return nil
	}
	defer uiaRelease(uia)

	DbgLog("fetchTabs: %#x ElementFromHandle uia=%#x", hwnd, uia)
	root := uiaElementFromHandle(uia, hwnd)
	DbgLog("fetchTabs: %#x root=%#x", hwnd, root)
	if root == 0 {
		return nil
	}
	defer uiaRelease(root)

	DbgLog("fetchTabs: %#x get_RawViewWalker", hwnd)
	walker := uiaRawViewWalker(uia)
	DbgLog("fetchTabs: %#x walker=%#x", hwnd, walker)
	if walker == 0 {
		return nil
	}
	defer uiaRelease(walker)

	items := collectTabItems(root, walker, 0)
	DbgLog("fetchTabs: %#x collectTabItems done: %d items", hwnd, len(items))
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

	walker := uiaRawViewWalker(uia)
	if walker == 0 {
		return
	}
	defer uiaRelease(walker)

	items := collectTabItems(root, walker, 0)
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
