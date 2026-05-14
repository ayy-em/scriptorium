@echo off
rem Unified Windows build entrypoint for Scriptorium.
rem
rem Usage:
rem   build
rem
rem Output:
rem   dist\ScriptoriumSetup.exe

call "%~dp0packaging\build_installer.bat"
