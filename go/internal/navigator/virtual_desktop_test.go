package navigator

import (
	"fmt"
	"testing"
)

// ---------------------------------------------------------------------------
// GUID helpers
// ---------------------------------------------------------------------------

func TestGUIDRoundtrip(t *testing.T) {
	cases := []string{
		"aa509086-5ca9-4c25-8f95-589d3c07b48a",
		"11111111-1111-1111-1111-111111111111",
		"ffffffff-ffff-ffff-ffff-ffffffffffff",
		"00000000-0000-0000-0000-000000000000",
		"6ba7b810-9dad-11d1-80b4-00c04fd430c8",
	}
	for _, s := range cases {
		guid, err := StringToGUID("{" + s + "}")
		if err != nil {
			t.Errorf("StringToGUID(%q) error: %v", s, err)
			continue
		}
		got := GUIDToString(guid)
		if got != s {
			t.Errorf("roundtrip %q → %q", s, got)
		}
	}
}

func TestStringToGUIDRejectsInvalid(t *testing.T) {
	cases := []string{"not-a-guid", "", "12345678-1234-1234-12"}
	for _, s := range cases {
		if _, err := StringToGUID(s); err == nil {
			t.Errorf("expected error for %q", s)
		}
	}
}

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

type mockManager struct {
	guidMap     map[uintptr]string
	currentHWNDs map[uintptr]bool
	failGet     map[uintptr]bool // HWNDs that return an error
}

func (m *mockManager) IsWindowOnCurrentVirtualDesktop(hwnd uintptr) (bool, error) {
	return m.currentHWNDs[hwnd], nil
}

func (m *mockManager) GetWindowDesktopID(hwnd uintptr) (string, error) {
	if m.failGet[hwnd] {
		return "", fmt.Errorf("COM failure for hwnd %d", hwnd)
	}
	g, ok := m.guidMap[hwnd]
	if !ok {
		return "", nil
	}
	return g, nil
}

func (m *mockManager) MoveWindowToDesktop(hwnd uintptr, guid string) error {
	return nil
}

type mockSwitcher struct {
	movedToCurrent []uintptr
	movedTo        []struct{ hwnd uintptr; n int }
	switchedTo     []int
	failCurrent    bool
	failSwitch     bool
}

func (s *mockSwitcher) MoveWindowToCurrent(hwnd uintptr) error {
	if s.failCurrent {
		return fmt.Errorf("move failed")
	}
	s.movedToCurrent = append(s.movedToCurrent, hwnd)
	return nil
}

func (s *mockSwitcher) MoveWindowTo(hwnd uintptr, n int) error {
	s.movedTo = append(s.movedTo, struct{ hwnd uintptr; n int }{hwnd, n})
	return nil
}

func (s *mockSwitcher) SwitchTo(n int) error {
	if s.failSwitch {
		return fmt.Errorf("switch failed")
	}
	s.switchedTo = append(s.switchedTo, n)
	return nil
}

func mockReader(current, all []byte) RegistryDesktopReader {
	return func() ([]byte, []byte, error) { return current, all, nil }
}

func failReader() RegistryDesktopReader {
	return func() ([]byte, []byte, error) { return nil, nil, fmt.Errorf("registry error") }
}

// guidBytes returns the 16-byte little-endian representation of a simple GUID string.
func guidBytes(s string) []byte {
	b, err := StringToGUID("{" + s + "}")
	if err != nil {
		panic(err)
	}
	return b[:]
}

// ---------------------------------------------------------------------------
// IsOnCurrentDesktop
// ---------------------------------------------------------------------------

func TestIsOnCurrentDesktopTrueWhenManagerNil(t *testing.T) {
	if !IsOnCurrentDesktop(12345, nil) {
		t.Error("expected true with nil manager")
	}
}

func TestIsOnCurrentDesktopTrueOnError(t *testing.T) {
	if !IsOnCurrentDesktop(12345, errManagerImpl{}) {
		t.Error("expected true on error")
	}
}

type errManagerImpl struct{}
func (errManagerImpl) IsWindowOnCurrentVirtualDesktop(_ uintptr) (bool, error) {
	return false, fmt.Errorf("COM failure")
}
func (errManagerImpl) GetWindowDesktopID(_ uintptr) (string, error) { return "", nil }
func (errManagerImpl) MoveWindowToDesktop(_ uintptr, _ string) error { return nil }

func TestIsOnCurrentDesktopReturnsFalse(t *testing.T) {
	m := &mockManager{guidMap: map[uintptr]string{}, currentHWNDs: map[uintptr]bool{12345: false}}
	if IsOnCurrentDesktop(12345, m) {
		t.Error("expected false")
	}
}

func TestIsOnCurrentDesktopReturnsTrue(t *testing.T) {
	m := &mockManager{guidMap: map[uintptr]string{}, currentHWNDs: map[uintptr]bool{12345: true}}
	if !IsOnCurrentDesktop(12345, m) {
		t.Error("expected true")
	}
}

// ---------------------------------------------------------------------------
// AssignDesktopNumbers
// ---------------------------------------------------------------------------

func TestAssignDesktopNumbersEmptyWhenManagerNil(t *testing.T) {
	nums, cur := AssignDesktopNumbers([]uintptr{1, 2, 3}, nil, nil)
	if len(nums) != 0 || len(cur) != 0 {
		t.Error("expected empty maps with nil manager")
	}
}

func TestAssignDesktopNumbersSameGUIDSameNumber(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-A", 3: "guid-B"},
		currentHWNDs: map[uintptr]bool{1: true, 2: true},
		failGet:      map[uintptr]bool{},
	}
	nums, _ := AssignDesktopNumbers([]uintptr{1, 2, 3}, m, nil)
	if nums[1] != nums[2] {
		t.Errorf("same GUID should give same number: %d vs %d", nums[1], nums[2])
	}
	if nums[3] == nums[1] {
		t.Errorf("different GUID should give different number")
	}
}

func TestAssignDesktopNumbersAreOneBased(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-B"},
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{},
	}
	nums, _ := AssignDesktopNumbers([]uintptr{1, 2}, m, nil)
	minN := nums[1]
	if nums[2] < minN {
		minN = nums[2]
	}
	if minN != 1 {
		t.Errorf("expected min number 1, got %d", minN)
	}
}

func TestAssignDesktopNumbersCurrentFlag(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-B"},
		currentHWNDs: map[uintptr]bool{1: true, 2: false},
		failGet:      map[uintptr]bool{},
	}
	_, cur := AssignDesktopNumbers([]uintptr{1, 2}, m, nil)
	if !cur[1] || cur[2] {
		t.Errorf("unexpected current flags: %v", cur)
	}
}

func TestAssignDesktopNumbersFollowRegistryOrder(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-B"},
		currentHWNDs: map[uintptr]bool{2: true},
		failGet:      map[uintptr]bool{},
	}
	// guid-B first in registry → desktop 1; guid-A → desktop 2
	nums, _ := AssignDesktopNumbers([]uintptr{1, 2}, m, []string{"guid-B", "guid-A"})
	if nums[2] != 1 {
		t.Errorf("guid-B should be desktop 1, got %d", nums[2])
	}
	if nums[1] != 2 {
		t.Errorf("guid-A should be desktop 2, got %d", nums[1])
	}
}

func TestAssignDesktopNumbersFallbackToEncounterOrder(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-B", 2: "guid-A"},
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{},
	}
	nums, _ := AssignDesktopNumbers([]uintptr{1, 2}, m, nil)
	if nums[1] != 1 {
		t.Errorf("first encountered guid-B should be desktop 1, got %d", nums[1])
	}
	if nums[2] != 2 {
		t.Errorf("second encountered guid-A should be desktop 2, got %d", nums[2])
	}
}

func TestAssignDesktopNumbersNilGUIDGivesZero(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A"}, // hwnd 2 not in map → returns ""
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{},
	}
	nums, cur := AssignDesktopNumbers([]uintptr{1, 2}, m, nil)
	if nums[2] != 0 {
		t.Errorf("unknown guid should give 0, got %d", nums[2])
	}
	if !cur[2] {
		t.Errorf("unknown guid should default is_current=true")
	}
}

func TestAssignDesktopNumbersPerWindowExceptionGivesZero(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A"},
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{2: true},
	}
	nums, cur := AssignDesktopNumbers([]uintptr{1, 2}, m, nil)
	if nums[1] <= 0 {
		t.Errorf("hwnd 1 should get valid number, got %d", nums[1])
	}
	if nums[2] != 0 {
		t.Errorf("failed hwnd should get 0, got %d", nums[2])
	}
	if !cur[2] {
		t.Error("failed hwnd should default is_current=true")
	}
}

func TestAssignDesktopNumbersGhostGUIDGivesMinusOne(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-B", 3: "guid-C"},
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{},
	}
	// guid-C is not in the registry list → ghost window → -1
	nums, cur := AssignDesktopNumbers([]uintptr{1, 2, 3}, m, []string{"guid-A", "guid-B"})
	if nums[1] != 1 {
		t.Errorf("guid-A should be 1, got %d", nums[1])
	}
	if nums[2] != 2 {
		t.Errorf("guid-B should be 2, got %d", nums[2])
	}
	if nums[3] != -1 {
		t.Errorf("guid-C (ghost) should be -1, got %d", nums[3])
	}
	if cur[3] {
		t.Error("ghost window should not be is_current")
	}
}

func TestAssignDesktopNumbersGhostGUIDFallbackWhenNoRegistry(t *testing.T) {
	m := &mockManager{
		guidMap:      map[uintptr]string{1: "guid-A", 2: "guid-B", 3: "guid-C"},
		currentHWNDs: map[uintptr]bool{1: true},
		failGet:      map[uintptr]bool{},
	}
	// No orderedGUIDs → sequential fallback, guid-C gets number 3
	nums, _ := AssignDesktopNumbers([]uintptr{1, 2, 3}, m, nil)
	if nums[3] != 3 {
		t.Errorf("without registry, guid-C should get sequential number 3, got %d", nums[3])
	}
}

// ---------------------------------------------------------------------------
// GetCurrentDesktopNumber
// ---------------------------------------------------------------------------

func TestGetCurrentDesktopNumberZeroWithNilReader(t *testing.T) {
	if n := GetCurrentDesktopNumber(nil); n != 0 {
		t.Errorf("expected 0, got %d", n)
	}
}

func TestGetCurrentDesktopNumberZeroOnError(t *testing.T) {
	if n := GetCurrentDesktopNumber(failReader()); n != 0 {
		t.Errorf("expected 0, got %d", n)
	}
}

func TestGetCurrentDesktopNumberFromMockedRegistry(t *testing.T) {
	g1 := "11111111-1111-1111-1111-111111111111"
	g2 := "22222222-2222-2222-2222-222222222222"
	g3 := "33333333-3333-3333-3333-333333333333"
	// Currently on g2 → expected desktop 2
	r := mockReader(guidBytes(g2), append(append(guidBytes(g1), guidBytes(g2)...), guidBytes(g3)...))
	if n := GetCurrentDesktopNumber(r); n != 2 {
		t.Errorf("expected 2, got %d", n)
	}
}

func TestGetCurrentDesktopNumberFirstDesktop(t *testing.T) {
	g1 := "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	g2 := "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
	r := mockReader(guidBytes(g1), append(guidBytes(g1), guidBytes(g2)...))
	if n := GetCurrentDesktopNumber(r); n != 1 {
		t.Errorf("expected 1, got %d", n)
	}
}

func TestGetCurrentDesktopNumberGUIDNotInList(t *testing.T) {
	g1 := "11111111-1111-1111-1111-111111111111"
	gUnknown := "ffffffff-ffff-ffff-ffff-ffffffffffff"
	r := mockReader(guidBytes(gUnknown), guidBytes(g1))
	if n := GetCurrentDesktopNumber(r); n != 0 {
		t.Errorf("expected 0 for unknown GUID, got %d", n)
	}
}

func TestGetCurrentDesktopNumberShortCurrentData(t *testing.T) {
	r := mockReader([]byte{0, 0, 0, 0, 0, 0, 0, 0}, make([]byte, 16))
	if n := GetCurrentDesktopNumber(r); n != 0 {
		t.Errorf("expected 0 for short current data, got %d", n)
	}
}

func TestGetCurrentDesktopNumberMisalignedAllData(t *testing.T) {
	g1 := "11111111-1111-1111-1111-111111111111"
	r := mockReader(guidBytes(g1), append(guidBytes(g1), 0))
	if n := GetCurrentDesktopNumber(r); n != 0 {
		t.Errorf("expected 0 for misaligned all data, got %d", n)
	}
}

// ---------------------------------------------------------------------------
// GetCurrentDesktopGUID
// ---------------------------------------------------------------------------

func TestGetCurrentDesktopGUIDNilReaderReturnsError(t *testing.T) {
	_, err := GetCurrentDesktopGUID(nil)
	if err == nil {
		t.Error("expected error with nil reader")
	}
}

func TestGetCurrentDesktopGUIDOnError(t *testing.T) {
	_, err := GetCurrentDesktopGUID(failReader())
	if err == nil {
		t.Error("expected error")
	}
}

func TestGetCurrentDesktopGUIDFromMockedRegistry(t *testing.T) {
	g1 := "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	r := func() ([]byte, []byte, error) { return guidBytes(g1), nil, nil }
	got, err := GetCurrentDesktopGUID(r)
	if err != nil {
		t.Fatal(err)
	}
	if got != g1 {
		t.Errorf("expected %q, got %q", g1, got)
	}
}

func TestGetCurrentDesktopGUIDReturnsErrorOnShortData(t *testing.T) {
	r := func() ([]byte, []byte, error) { return []byte{0, 0, 0, 0, 0, 0, 0, 0}, nil, nil }
	_, err := GetCurrentDesktopGUID(r)
	if err == nil {
		t.Error("expected error for short data")
	}
}

// ---------------------------------------------------------------------------
// GetRegistryDesktopOrder
// ---------------------------------------------------------------------------

func TestGetRegistryDesktopOrderNilReturnsNil(t *testing.T) {
	if GetRegistryDesktopOrder(nil) != nil {
		t.Error("expected nil")
	}
}

func TestGetRegistryDesktopOrderErrorReturnsNil(t *testing.T) {
	if GetRegistryDesktopOrder(failReader()) != nil {
		t.Error("expected nil on error")
	}
}

func TestGetRegistryDesktopOrderFromMockedRegistry(t *testing.T) {
	g1 := "11111111-1111-1111-1111-111111111111"
	g2 := "22222222-2222-2222-2222-222222222222"
	r := func() ([]byte, []byte, error) {
		return nil, append(guidBytes(g1), guidBytes(g2)...), nil
	}
	got := GetRegistryDesktopOrder(r)
	if len(got) != 2 || got[0] != g1 || got[1] != g2 {
		t.Errorf("unexpected order: %v", got)
	}
}

func TestGetRegistryDesktopOrderMisalignedReturnsNil(t *testing.T) {
	r := func() ([]byte, []byte, error) { return nil, make([]byte, 17), nil }
	if GetRegistryDesktopOrder(r) != nil {
		t.Error("expected nil for misaligned data")
	}
}

func TestGetRegistryDesktopOrderEmptyReturnsNil(t *testing.T) {
	r := func() ([]byte, []byte, error) { return nil, []byte{}, nil }
	if GetRegistryDesktopOrder(r) != nil {
		t.Error("expected nil for empty data")
	}
}

// ---------------------------------------------------------------------------
// MoveWindowToCurrentDesktop
// ---------------------------------------------------------------------------

func TestMoveWindowReturnsFalseWhenBothNil(t *testing.T) {
	if MoveWindowToCurrentDesktop(12345, nil, nil, nil) {
		t.Error("expected false")
	}
}

func TestMoveWindowReturnsFalseWhenManagerNilAndSwitcherFails(t *testing.T) {
	s := &mockSwitcher{failCurrent: true}
	if MoveWindowToCurrentDesktop(12345, s, nil, nil) {
		t.Error("expected false")
	}
}

func TestMoveWindowReturnsFalseWhenGUIDUnavailable(t *testing.T) {
	m := &mockManager{guidMap: map[uintptr]string{}, currentHWNDs: map[uintptr]bool{}, failGet: map[uintptr]bool{}}
	getGUID := func() (string, error) { return "", fmt.Errorf("no GUID") }
	if MoveWindowToCurrentDesktop(12345, nil, m, getGUID) {
		t.Error("expected false")
	}
}

func TestMoveWindowCallsManagerMoveToDesktop(t *testing.T) {
	targetGUID := "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	cm := &capManager{}
	mgr := capVDManager{cap: cm}
	getGUID := func() (string, error) { return targetGUID, nil }
	result := MoveWindowToCurrentDesktop(99, nil, mgr, getGUID)
	if !result {
		t.Error("expected true")
	}
	if cm.movedHWND != 99 || cm.movedGUID != targetGUID {
		t.Errorf("unexpected move: hwnd=%d guid=%q", cm.movedHWND, cm.movedGUID)
	}
}

type capManager struct {
	movedHWND uintptr
	movedGUID string
}

type capVDManager struct {
	cap *capManager
}

func (c capVDManager) IsWindowOnCurrentVirtualDesktop(_ uintptr) (bool, error) { return true, nil }
func (c capVDManager) GetWindowDesktopID(_ uintptr) (string, error)            { return "", nil }
func (c capVDManager) MoveWindowToDesktop(hwnd uintptr, guid string) error {
	c.cap.movedHWND = hwnd
	c.cap.movedGUID = guid
	return nil
}

func TestMoveWindowUseSwitcherFirst(t *testing.T) {
	s := &mockSwitcher{}
	result := MoveWindowToCurrentDesktop(42, s, nil, nil)
	if !result {
		t.Error("expected true via switcher")
	}
	if len(s.movedToCurrent) != 1 || s.movedToCurrent[0] != 42 {
		t.Errorf("expected switcher.MoveWindowToCurrent(42), got %v", s.movedToCurrent)
	}
}

func TestMoveWindowManagerRaisesReturnsFalse(t *testing.T) {
	targetGUID := "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	getGUID := func() (string, error) { return targetGUID, nil }
	m := errMoveManager{}
	if MoveWindowToCurrentDesktop(99, nil, m, getGUID) {
		t.Error("expected false when manager raises")
	}
}

type errMoveManager struct{}

func (errMoveManager) IsWindowOnCurrentVirtualDesktop(_ uintptr) (bool, error) { return true, nil }
func (errMoveManager) GetWindowDesktopID(_ uintptr) (string, error)            { return "", nil }
func (errMoveManager) MoveWindowToDesktop(_ uintptr, _ string) error {
	return fmt.Errorf("COM failure")
}

// ---------------------------------------------------------------------------
// SwitchToDesktopNumber
// ---------------------------------------------------------------------------

func TestSwitchToDesktopNumberSucceeds(t *testing.T) {
	s := &mockSwitcher{}
	if !SwitchToDesktopNumber(3, s) {
		t.Error("expected true")
	}
	if len(s.switchedTo) != 1 || s.switchedTo[0] != 3 {
		t.Errorf("expected SwitchTo(3), got %v", s.switchedTo)
	}
}

func TestSwitchToDesktopNumberFalseOnNilSwitcher(t *testing.T) {
	if SwitchToDesktopNumber(1, nil) {
		t.Error("expected false with nil switcher")
	}
}

func TestSwitchToDesktopNumberFalseOnError(t *testing.T) {
	s := &mockSwitcher{failSwitch: true}
	if SwitchToDesktopNumber(2, s) {
		t.Error("expected false when switch fails")
	}
}

// ---------------------------------------------------------------------------
// MoveWindowToAdjacentDesktop
// ---------------------------------------------------------------------------

func TestMoveToAdjacentLeftBoundaryReturnsZero(t *testing.T) {
	order := []string{"g1", "g2", "g3"}
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, -1, s,
		func() []string { return order },
		func() int { return 1 },
	)
	if n != 0 {
		t.Errorf("expected 0 at left boundary, got %d", n)
	}
}

func TestMoveToAdjacentRightBoundaryReturnsZero(t *testing.T) {
	order := []string{"g1", "g2", "g3"}
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, +1, s,
		func() []string { return order },
		func() int { return 3 },
	)
	if n != 0 {
		t.Errorf("expected 0 at right boundary, got %d", n)
	}
}

func TestMoveToAdjacentRightReturnsTarget(t *testing.T) {
	order := []string{"g1", "g2", "g3"}
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, +1, s,
		func() []string { return order },
		func() int { return 1 },
	)
	if n != 2 {
		t.Errorf("expected 2, got %d", n)
	}
}

func TestMoveToAdjacentLeftReturnsTarget(t *testing.T) {
	order := []string{"g1", "g2", "g3"}
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, -1, s,
		func() []string { return order },
		func() int { return 3 },
	)
	if n != 2 {
		t.Errorf("expected 2, got %d", n)
	}
}

func TestMoveToAdjacentCallsWindowMove(t *testing.T) {
	order := []string{"g1", "g2"}
	s := &mockSwitcher{}
	MoveWindowToAdjacentDesktop(777, +1, s,
		func() []string { return order },
		func() int { return 1 },
	)
	if len(s.movedTo) == 0 || s.movedTo[0].hwnd != 777 {
		t.Errorf("expected MoveWindowTo(777, ...), got %v", s.movedTo)
	}
}

func TestMoveToAdjacentNilRegistryReturnsZero(t *testing.T) {
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, +1, s, nil, func() int { return 1 })
	if n != 0 {
		t.Errorf("expected 0, got %d", n)
	}
}

func TestMoveToAdjacentEmptyRegistryReturnsZero(t *testing.T) {
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, +1, s,
		func() []string { return []string{} },
		func() int { return 1 },
	)
	if n != 0 {
		t.Errorf("expected 0, got %d", n)
	}
}

func TestMoveToAdjacentUnknownCurrentReturnsZero(t *testing.T) {
	order := []string{"g1", "g2"}
	s := &mockSwitcher{}
	n := MoveWindowToAdjacentDesktop(99, +1, s,
		func() []string { return order },
		func() int { return 0 },
	)
	if n != 0 {
		t.Errorf("expected 0, got %d", n)
	}
}

func TestMoveToAdjacentSwitcherErrorStillReturnsTarget(t *testing.T) {
	order := []string{"g1", "g2", "g3"}
	s := &mockSwitcher{failSwitch: true}
	s.movedTo = append(s.movedTo, struct{ hwnd uintptr; n int }{}) // pre-fill to not panic
	s.movedTo = s.movedTo[:0]
	// Even if switcher.SwitchTo fails, target is returned
	n := MoveWindowToAdjacentDesktop(99, +1, s,
		func() []string { return order },
		func() int { return 2 },
	)
	if n != 3 {
		t.Errorf("expected 3, got %d", n)
	}
}
