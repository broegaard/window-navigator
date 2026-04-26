//go:build windows

package navigator

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

var _dbgFile *os.File

// InitDebugLog opens %TEMP%\windows-navigator-debug.log for writing.
// Each call truncates the file so the log always reflects the latest run.
func InitDebugLog() {
	tmp := os.Getenv("TEMP")
	if tmp == "" {
		tmp = os.Getenv("TMP")
	}
	if tmp == "" {
		tmp = `C:\Temp`
	}
	path := filepath.Join(tmp, "windows-navigator-debug.log")
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
	if err != nil {
		return
	}
	_dbgFile = f
	DbgLog("=== windows-navigator debug log started ===")
}

// DbgLog writes a timestamped line to stderr and the debug log file, flushing immediately.
// stderr is visible in the terminal when the binary is built without -H windowsgui.
func DbgLog(format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	line := fmt.Sprintf("[%s] %s\n", time.Now().Format("15:04:05.000"), msg)
	fmt.Fprint(os.Stderr, line)
	if _dbgFile != nil {
		fmt.Fprint(_dbgFile, line)
		_dbgFile.Sync()
	}
}
