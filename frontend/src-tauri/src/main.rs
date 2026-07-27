// Tauri desktop shell. On startup it launches the FastAPI backend as a
// child process (bound to 0.0.0.0:8420 so phones on the same LAN can
// reach it too), and points the webview at the Vite-built frontend,
// which talks to that same backend via the /api proxy path.
//
// Packaging note: for a distributable build, bundle the backend as a
// PyInstaller-built binary and register it as a Tauri "sidecar" via
// tauri.conf.json's bundle.externalBin instead of shelling out to a
// system Python — this dev version assumes a Python environment with
// requirements.txt already installed for simplicity during development.

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn spawn_backend() -> std::io::Result<Child> {
    Command::new("python3")
        .args(["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8420"])
        .current_dir("../backend")
        .spawn()
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let child = spawn_backend().expect("failed to start LocalRP backend");
            app.manage(BackendProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .on_window_event(|event| {
            if let tauri::WindowEvent::Destroyed = event.event() {
                let state: tauri::State<BackendProcess> = event.window().state();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running LocalRP");
}
