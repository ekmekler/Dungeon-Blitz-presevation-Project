### Usage

Drop the file `mm.cfg` in `%USERPROFILE%` directory as that turns on debugging in flash.

then read the logs in real time in powershell:

```
get-content "$env:APPDATA\Macromedia\Flash Player\Logs\flashlog.txt" -wait -tail 1
```

or

```sh
vim "$HOME/.wine/drive_c/users/$USER/AppData/Roaming/Macromedia/Flash Player/Logs/flashlog.txt"
```

### Credit

Coldice(cold.ic) for giving me the Flash debugger files.
