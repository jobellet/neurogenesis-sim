# Code Signing Guide for Neurogenesis Desktop (Windows & Linux)

This document outlines the code signing requirements, toolchains, and CI integration for official releases of the cross-platform Neurogenesis desktop application.

---

## 1. Security Policy & Invariants
- **No Secrets in Repository**: Certificates, private keys, and passphrases must **never** be committed to version control.
- **Graceful Fallback**: The build and packaging scripts run cleanly without signing keys. CI automatically detects whether signing secrets are present in repository secrets; if absent (such as in external PRs or fork builds), packages remain unsigned and CI continues without error.

---

## 2. Windows Authenticode Signing

### What is Needed
1. A valid Authenticode Code Signing Certificate:
   - **Standard Code Signing Certificate** or **Extended Validation (EV) Certificate** (or Cloud HSM like Azure Key Vault / DigiCert ONE).
   - Exported as a password-protected `.pfx` file or accessed via PKCS#11 / Azure Key Vault SignTool.
2. `signtool.exe` (included in the Windows SDK and Visual Studio Build Tools).
3. RFC 3161 compliant timestamp server (e.g. `http://timestamp.digicert.com`).

### Manual Signing Command
To sign the application executable and the Inno Setup installer:
```powershell
signtool.exe sign /f "path\to\certificate.pfx" /p "YourPassword" `
    /tr "http://timestamp.digicert.com" /td sha256 /fd sha256 `
    /d "Neurogenesis Desktop Application" `
    "publish\win-x64\Neurogenesis.exe"

signtool.exe sign /f "path\to\certificate.pfx" /p "YourPassword" `
    /tr "http://timestamp.digicert.com" /td sha256 /fd sha256 `
    /d "Neurogenesis Setup" `
    "dist\Neurogenesis-setup-win-x64.exe"
```

### Windows SmartScreen
- Windows SmartScreen evaluates reputation based on digital signatures and download volumes.
- Binaries signed with an EV certificate or established Standard certificate bypass Defender SmartScreen warnings ("Windows protected your PC").

### CI Integration (GitHub Secrets)
To enable automated signing in `.github/workflows/avalonia-app.yml`, configure the following repository secrets:
- `WINDOWS_SIGNING_CERT_BASE64`: Base64-encoded `.pfx` certificate file.
- `WINDOWS_SIGNING_PASSWORD`: Password for the `.pfx` file.

---

## 3. Linux AppImage Signing

### What is Needed
1. A GPG keypair for the project or organization.
2. `gpg` installed on the runner.

### Signing the AppImage
A detached ASCII-armored signature is created for the AppImage:
```bash
gpg --batch --yes --detach-sign --armor --output "dist/Neurogenesis-x86_64.AppImage.asc" "dist/Neurogenesis-x86_64.AppImage"
```

Users can verify the signature against the project public key:
```bash
gpg --verify Neurogenesis-x86_64.AppImage.asc Neurogenesis-x86_64.AppImage
```

### CI Integration (GitHub Secrets)
- `GPG_SIGNING_KEY`: Armored private GPG key.
- `GPG_PASSPHRASE`: Passphrase for the key (if applicable).
