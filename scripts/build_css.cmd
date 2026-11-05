@echo off
rem Builds frontend\css\tailwind.css from frontend\css\tailwind.input.css and the Tailwind classes in
rem frontend\index.html and frontend\js\*.js, with Tailwind's standalone program (no npm).
rem The program is downloaded once into .tools\ (git-ignored).   scripts\build_css.cmd [--watch]
setlocal
set VERSION=4.1.14
set ROOT=%~dp0..
set TOOL=%ROOT%\.tools\tailwindcss-%VERSION%.exe
if not exist "%TOOL%" (
  if not exist "%ROOT%\.tools" mkdir "%ROOT%\.tools"
  echo Downloading Tailwind CSS v%VERSION% ...
  curl -fsSL -o "%TOOL%" "https://github.com/tailwindlabs/tailwindcss/releases/download/v%VERSION%/tailwindcss-windows-x64.exe" || exit /b 1
)
cd /d "%ROOT%\frontend"
"%TOOL%" -i css\tailwind.input.css -o css\tailwind.css --minify %*
