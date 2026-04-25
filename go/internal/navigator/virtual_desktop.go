package navigator

import (
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"strings"
)

var _ = hex.EncodeToString // used only in StringToGUID

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

// VirtualDesktopManager is the DIP boundary for the COM IVirtualDesktopManager.
// Nil manager is valid — all callers treat it as "unavailable, fail open".
type VirtualDesktopManager interface {
	IsWindowOnCurrentVirtualDesktop(hwnd uintptr) (bool, error)
	GetWindowDesktopID(hwnd uintptr) (string, error) // lowercase UUID without braces; "" + err if unknown
	MoveWindowToDesktop(hwnd uintptr, desktopGUID string) error
}

// DesktopSwitcher abstracts pyvda / IVirtualDesktopManagerInternal on Windows.
// MoveWindowToCurrent moves hwnd to the current desktop (pyvda AppView.move).
// MoveWindowTo moves hwnd to desktop n and is a best-effort call.
// SwitchTo switches to desktop n (pyvda VirtualDesktop.go).
type DesktopSwitcher interface {
	MoveWindowToCurrent(hwnd uintptr) error
	MoveWindowTo(hwnd uintptr, n int) error
	SwitchTo(n int) error
}

// RegistryDesktopReader reads the virtual desktop registry values.
// Returns (currentGUID 16 bytes LE, allGUIDs N*16 bytes LE, error).
type RegistryDesktopReader func() (current []byte, all []byte, err error)

// ---------------------------------------------------------------------------
// GUID helpers (Windows little-endian byte layout ↔ UUID string)
// ---------------------------------------------------------------------------

// GUIDToString converts 16 raw bytes in Windows GUID layout to a lowercase UUID string.
// Windows layout: Data1 (4 LE) | Data2 (2 LE) | Data3 (2 LE) | Data4 (8 BE).
func GUIDToString(b [16]byte) string {
	d1 := binary.LittleEndian.Uint32(b[0:4])
	d2 := binary.LittleEndian.Uint16(b[4:6])
	d3 := binary.LittleEndian.Uint16(b[6:8])
	return fmt.Sprintf("%08x-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",
		d1, d2, d3,
		b[8], b[9],
		b[10], b[11], b[12], b[13], b[14], b[15])
}

// StringToGUID parses a UUID string (with or without curly braces) into Windows GUID bytes.
func StringToGUID(s string) ([16]byte, error) {
	s = strings.Trim(s, "{}")
	parts := strings.Split(s, "-")
	if len(parts) != 5 {
		return [16]byte{}, fmt.Errorf("invalid GUID %q", s)
	}
	joined := parts[0] + parts[1] + parts[2] + parts[3] + parts[4]
	if len(joined) != 32 {
		return [16]byte{}, fmt.Errorf("invalid GUID length %q", s)
	}
	raw, err := hex.DecodeString(joined)
	if err != nil {
		return [16]byte{}, fmt.Errorf("invalid GUID hex %q: %w", s, err)
	}
	// raw is big-endian; convert first three fields to little-endian
	var b [16]byte
	d1 := binary.BigEndian.Uint32(raw[0:4])
	d2 := binary.BigEndian.Uint16(raw[4:6])
	d3 := binary.BigEndian.Uint16(raw[6:8])
	binary.LittleEndian.PutUint32(b[0:4], d1)
	binary.LittleEndian.PutUint16(b[4:6], d2)
	binary.LittleEndian.PutUint16(b[6:8], d3)
	copy(b[8:], raw[8:])
	return b, nil
}

// bytesToGUIDString decodes 16 raw bytes directly to UUID string without the [16]byte intermediate.
func bytesToGUIDString(b []byte) string {
	var arr [16]byte
	copy(arr[:], b)
	return GUIDToString(arr)
}

// ---------------------------------------------------------------------------
// Registry-based desktop queries (injectable for testing)
// ---------------------------------------------------------------------------

// GetRegistryDesktopOrder returns GUIDs of all desktops in display order.
// Returns nil on any failure.
func GetRegistryDesktopOrder(read RegistryDesktopReader) []string {
	if read == nil {
		return nil
	}
	_, all, err := read()
	if err != nil {
		return nil
	}
	if len(all) == 0 || len(all)%16 != 0 {
		return nil
	}
	guids := make([]string, len(all)/16)
	for i := range guids {
		guids[i] = bytesToGUIDString(all[i*16 : i*16+16])
	}
	return guids
}

// GetCurrentDesktopGUID returns the UUID string of the current virtual desktop,
// read from the registry. Returns ("", err) on failure.
func GetCurrentDesktopGUID(read RegistryDesktopReader) (string, error) {
	if read == nil {
		return "", fmt.Errorf("no registry reader")
	}
	current, _, err := read()
	if err != nil {
		return "", err
	}
	if len(current) != 16 {
		return "", fmt.Errorf("current GUID data is %d bytes, want 16", len(current))
	}
	return bytesToGUIDString(current), nil
}

// GetCurrentDesktopNumber returns the 1-based number of the active desktop, 0 on failure.
func GetCurrentDesktopNumber(read RegistryDesktopReader) int {
	if read == nil {
		return 0
	}
	current, all, err := read()
	if err != nil {
		return 0
	}
	if len(current) != 16 || len(all) == 0 || len(all)%16 != 0 {
		return 0
	}
	curGUID := bytesToGUIDString(current)
	for i := 0; i < len(all)/16; i++ {
		if bytesToGUIDString(all[i*16:i*16+16]) == curGUID {
			return i + 1
		}
	}
	return 0
}

// ---------------------------------------------------------------------------
// Virtual desktop operations (injectable for testing)
// ---------------------------------------------------------------------------

// IsOnCurrentDesktop returns true if hwnd is on the current virtual desktop.
// Returns true on failure — fail-open so the window is always shown.
func IsOnCurrentDesktop(hwnd uintptr, manager VirtualDesktopManager) bool {
	if manager == nil {
		return true
	}
	ok, err := manager.IsWindowOnCurrentVirtualDesktop(hwnd)
	if err != nil {
		return true
	}
	return ok
}

// AssignDesktopNumbers maps each hwnd to a 1-based desktop number and an is-current flag.
// orderedGUIDs is from GetRegistryDesktopOrder; pass nil to fall back to encounter order.
// Returns empty maps if manager is nil.
func AssignDesktopNumbers(
	hwnds []uintptr,
	manager VirtualDesktopManager,
	orderedGUIDs []string,
) (numbers map[uintptr]int, isCurrent map[uintptr]bool) {
	numbers = make(map[uintptr]int)
	isCurrent = make(map[uintptr]bool)

	if manager == nil {
		return
	}

	guidToNumber := make(map[string]int)
	for i, g := range orderedGUIDs {
		guidToNumber[g] = i + 1
	}

	for _, hwnd := range hwnds {
		func() {
			defer func() {
				if r := recover(); r != nil {
					numbers[hwnd] = 0
					isCurrent[hwnd] = true
				}
			}()
			guid, err := manager.GetWindowDesktopID(hwnd)
			if err != nil || guid == "" {
				numbers[hwnd] = 0
				isCurrent[hwnd] = true
				return
			}
			n, ok := guidToNumber[guid]
			if !ok {
				n = len(guidToNumber) + 1
				guidToNumber[guid] = n
			}
			numbers[hwnd] = n
			ok2, err2 := manager.IsWindowOnCurrentVirtualDesktop(hwnd)
			if err2 != nil {
				isCurrent[hwnd] = true
			} else {
				isCurrent[hwnd] = ok2
			}
		}()
	}
	return
}

// MoveWindowToCurrentDesktop moves hwnd to the current virtual desktop.
// Tries switcher.MoveWindowToCurrent first; falls back to manager + getGUID.
func MoveWindowToCurrentDesktop(
	hwnd uintptr,
	switcher DesktopSwitcher,
	manager VirtualDesktopManager,
	getGUID func() (string, error),
) bool {
	if switcher != nil {
		if err := switcher.MoveWindowToCurrent(hwnd); err == nil {
			return true
		}
	}
	if manager == nil {
		return false
	}
	if getGUID == nil {
		return false
	}
	guid, err := getGUID()
	if err != nil || guid == "" {
		return false
	}
	if err := manager.MoveWindowToDesktop(hwnd, guid); err != nil {
		return false
	}
	return true
}

// SwitchToDesktopNumber switches to the Nth virtual desktop (1-based).
func SwitchToDesktopNumber(n int, switcher DesktopSwitcher) bool {
	if switcher == nil {
		return false
	}
	return switcher.SwitchTo(n) == nil
}

// MoveWindowToAdjacentDesktop moves hwnd to the adjacent desktop and switches to it.
// direction: +1 for right, -1 for left. Returns target desktop number, 0 at boundary.
func MoveWindowToAdjacentDesktop(
	hwnd uintptr,
	direction int,
	switcher DesktopSwitcher,
	getOrder func() []string,
	getCurrentN func() int,
) int {
	if getOrder == nil || getCurrentN == nil {
		return 0
	}
	order := getOrder()
	if len(order) == 0 {
		return 0
	}
	currentN := getCurrentN()
	if currentN <= 0 {
		return 0
	}
	targetN := currentN + direction
	if targetN < 1 || targetN > len(order) {
		return 0
	}
	if switcher != nil {
		_ = switcher.MoveWindowTo(hwnd, targetN) // best-effort; ignore error
		_ = switcher.SwitchTo(targetN)
	}
	return targetN
}
