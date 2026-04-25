// Regenerate rsrc.syso after editing app.manifest:
//
//go:generate go run github.com/akavel/rsrc@v0.10.2 -manifest app.manifest -o rsrc.syso

package main

import "github.com/kbs/windows-navigator/internal/navigator"

func main() {
	navigator.RunApp()
}
