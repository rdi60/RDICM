# Publish the source to GitHub (Windows PowerShell)

The `.bundle` file supplied alongside the ZIP is a complete Git history containing the v0.3 development commit. The connected GitHub repository `rdi60/RDICM` was reported empty when checked.

1. Save `rajan_dental_v0_3_full_source.bundle` to your Downloads folder.
2. Open PowerShell in Downloads and run:

```powershell
git clone .\rajan_dental_v0_3_full_source.bundle .\RajanDentalSource
cd .\RajanDentalSource
git remote set-url origin https://github.com/rdi60/RDICM.git
git push -u origin main
```

If the remote has since received new commits, inspect it and merge carefully rather than force pushing. Confirm the full source files are visible in GitHub afterward. The GitHub repo is public; do not add any patient data, secrets or local databases.
