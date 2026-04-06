# VPS Workflow

Quy uoc lam viec mac dinh cua repo nay la `VPS-first`.

## 1) Nguyen tac bat buoc

- Ban dang chay that va nguon su that uu tien la repo tren VPS: `/root/notary_v2`.
- Mac dinh moi thao tac van hanh, kiem tra, restart, xem log va sua truc tiep ban dang chay deu lam tren VPS.
- Local chi dung khi:
  - can chuan bi commit/push,
  - can soan tai lieu/script ho tro,
  - hoac nguoi dung noi ro la muon lam local.
- Neu local, `origin`, va VPS khac nhau, phai xac minh ben nao moi nhat truoc khi sua.

## 2) Cach giu quy uoc nay qua chat khac

- Commit va push cac file quy uoc nay len repo:
  - `CLAUDE.md`
  - `docs/VPS_WORKFLOW.md`
  - cac script wrapper `launch_vps_app.bat`, `view_vps_logs.bat`
- Khi mo chat moi, uu tien noi ro ngay cau dau:
  - `Doc CLAUDE.md va docs/VPS_WORKFLOW.md. Lam viec tren VPS, khong sua local tru khi toi noi ro.`
- Neu agent chua doc repo, nhac lai nguyen tac `VPS-first` thay vi gia dinh no tu nho duoc tu chat cu.

## 3) Cach giu quy uoc nay qua may khac

### Cach nhanh cho may Windows moi

1. Clone repo.
2. Tao file `deploy/vps/ssh_credentials.env` tu `deploy/vps/ssh_credentials.example`.
3. Dien dung:
   - `VPS_HOST`
   - `VPS_PORT`
   - `VPS_USER`
   - `VPS_PASSWORD`
   - `VPS_HOSTKEY`
   - `VPS_REPO_DIR` (mac dinh: `~/notary_v2`)
4. Dung cac lenh/root wrapper sau:
   - `launch_vps_app.bat`: restart/check app va mo browser
   - `connect_vps.bat`: vao SSH shell tren VPS
   - `view_vps_logs.bat`: stream log `web` va `worker`

### Cach ben vung hon

- Dung SSH key thay vi password.
- Luu secret trong password manager hoac co che quan ly secret noi bo.
- Khong commit `deploy/vps/ssh_credentials.env` neu khong that su can thiet.

## 4) Quy trinh lam viec mac dinh

### Mo app

```bat
launch_vps_app.bat
```

### Vao shell VPS

```bat
connect_vps.bat
```

### Xem log live

```bat
view_vps_logs.bat
```

### Sau khi vao VPS

```bash
cd /root/notary_v2
git status --short --branch
bash deploy/vps/manage_services.sh status
```

### Sau khi sua code tren VPS

```bash
cd /root/notary_v2
bash install_vps.sh --skip-system-packages
bash deploy/vps/manage_services.sh restart
bash deploy/vps/manage_services.sh logs
```

## 5) Quy tac dong bo

- Neu sua tren VPS va muon luu lau dai, commit/push tu ban dang dung tren VPS hoac dong bo ve local ngay sau do.
- Khong tiep tuc sua tren local neu chua biet local co trung voi VPS hay khong.
- Truoc khi quay lai local:
  - fetch/pull,
  - so commit local voi `origin`,
  - neu can, so tiep voi repo tren VPS.

## 6) Checklist nhanh cho moi phien lam viec

```text
1. Xac nhan dang lam tren VPS, khong phai local.
2. Xac nhan repo dir: /root/notary_v2
3. Kiem tra git status
4. Kiem tra service status
5. Sua / restart / xem logs tren VPS
6. Neu thay doi can giu, commit + push
```
