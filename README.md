# Personal Operator Workspace & Configurations

> ⚠️ **PENTING UNTUK PENGGUNA UMUM / TEMAN:**  
> Folder ini **hanya untuk Operator/Pemilik repository**. Jika kamu meng-clone repo ini untuk digunakan sendiri atau temanmu mencoba tools ini, **jangan gunakan isi folder ini**.  
> Semua tools publik untuk pengguna umum berada di menu utama KancaHub dengan **zero-setup** menggunakan **Temp Mail (Mail.tm)** dan **Guerrilla Mail**.

---

## Mengapa Folder Ini Dipisahkan?

Saat teman atau pengguna lain mencoba tools di repository ini, mereka sebelumnya mengalami kegagalan karena beberapa fitur mengasumsikan keberadaan infrastruktur pribadi milik operator:
1. **Domain Email Pribadi (`@kancalabs.my.id` / `@kancalabs.biz.id`)**:  
   Dikelola melalui Cloudflare Worker Tempik dan relay Supabase pribadi. Pengguna lain tidak memiliki akses baca ke inbox domain ini.
2. **Cloudflare Workers AI Stack (`signup_from_scratch/`)**:  
   Bergantung pada endpoint Supabase pribadi (`https://jkqjmkkwfrgfskwlxpyc.supabase.co`) dengan API key privat dan proteksi Cloudflare Turnstile.
3. **Akun Sekolah / Kampus (`binus.ac.id`)**:  
   Email edukasi milik operator (`raymondi@binus.ac.id`) untuk klaim GitHub Student Developer Pack.
4. **Sesi Browser Lokal (Brave KWallet)**:  
   Ekstraksi cookie terenkripsi milik akun operator (`lithium7b@gmail.com`).
5. **Saldo Berbayar (Litensi API)**:  
   Layanan aktivasi SMS/OTP berbayar milik operator.

---

## Struktur Folder `personal/`

```
personal/
├── cloudflare/   # Cloudflare AI custom stack & script wrapper privat
├── domains/      # Konfigurasi & dokumentasi domain kancalabs.my.id & biz.id
├── school/       # Alur farm & verifikasi akun edukasi binus.ac.id
└── sessions/     # Helper ekstraksi sesi terenkripsi browser lokal operator
```

---

## Perbandingan: Mode User (Publik) vs Mode Personal (Operator)

| Aspek | Mode User (Publik / Teman) | Mode Personal (Operator) |
|---|---|---|
| **Email Disposable** | **Temp Mail (`mail.tm`)** & **Guerrilla Mail** | `kancalabs.my.id` (Tempik) / `biz.id` |
| **Setup & Prasyarat** | **0 (Zero Setup)** — Langsung jalan di komputer mana saja | Butuh domain, worker Cloudflare & Supabase |
| **Inference AI Gratis** | OpenCode Standalone, 0xgetz Harvesters, Dahl 100M | Cloudflare Workers AI via private relay |
| **Browser & Sesi** | Sesi terisolasi mandiri | Brave browser KWallet operator |
| **Lokasi Script** | Menu utama `kancahub` & `scripts/` | `personal/` & flag `--personal` |
