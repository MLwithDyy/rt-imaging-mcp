# Dua bug bias di kode DVH-ku, ditemukan dengan phantom yang punya jawaban eksak

Aku membuat **rt-imaging-mcp**, server MCP lokal yang hanya-baca untuk file DICOM, NIfTI, dan data radioterapi, supaya agen AI bisa memeriksa data pencitraan tanpa membawa data pasien ke model. Salah satu tool-nya menghitung metrik dosis-volume (D95, V20, dan seterusnya) untuk satu struktur. Tulisan ini bukan tentang server-nya. Ini tentang satu pertanyaan yang tidak punya jawaban mudah: **bagaimana tahu bahwa angka DVH yang kuhitung benar?**

Repo: https://github.com/MLwithDyy/rt-imaging-mcp. Paket: https://pypi.org/project/rt-imaging-mcp/.

## Masalahnya: tidak ada kebenaran dasar

Sistem perencanaan (TPS) tidak kupunya. Yang kupunya: satu pustaka sumber terbuka yang mapan (dicompyler-core), data publik dari The Cancer Imaging Archive, dan kemampuan membuat phantom sintetis. Perbandingan dengan alat lain bukan bukti kebenaran. Kalau dua program setuju, keduanya bisa salah dengan cara yang sama. Jadi aku memakai tiga lapis: tes dengan jawaban hitungan tangan, phantom dengan jawaban analitik, dan perbandingan pada data nyata.

## Data nyata langsung menolak alatku

Tiga pasien dari koleksi Pancreatic-CT-CBCT-SEG (TCIA, CC BY 4.0) (sitasi lengkap di akhir tulisan). Run pertama: semua pasangan struktur-dosis **ditolak** dengan pesan `computation exceeds the work limit`.

Penyebabnya ada di kodeku. Rasteriser yang mengubah kontur menjadi mask pada grid dosis berbiaya sel × sisi poligon. Kontur manual organ rapat (ratusan titik) dan grid dosis halus, jadi satu kontur 600 titik di 100 irisan sudah memakai 342 juta unit kerja dari batas 400 juta. Phantom kubus tidak pernah menunjukkan ini.

Perbaikannya: algoritma garis-pindai (biaya sel + persilangan). Hasilnya identik dengan versi lama pada 4000 poligon acak (termasuk kasus batas yang sulit: titik pusat tepat di tepi, sisi horizontal, titik ganda), sekitar 44 kali lebih cepat pada kontur 1000 titik. Versi lama kujadikan *oracle* di dalam tes.

## Run kedua: ada pola, dan pola itu petunjuk

Setelah berjalan, 39 struktur dibandingkan dengan dicompyler-core. Kebanyakan cocok, tapi beberapa selisih besar (D95 sampai 1,7 Gy). Aku menambah dua kolom ke keluaran: ukuran voxel dan jarak irisan kontur. Polanya langsung terlihat:

| Pasien | Irisan dosis | Irisan kontur | Hasil |
|---|---|---|---|
| 1 | 1,5 mm | 3 mm | selisih besar pada struktur kecil |
| 2 | 1 mm | 2 mm | selisih besar pada struktur kecil |
| 3 | 3 mm | 3 mm | cocok dalam 0,02 Gy |

Selisih besar hanya muncul ketika irisan dosis dua kali lebih rapat dari irisan kontur.

## Phantom dengan jawaban eksak

Aku membuat phantom dengan geometri itu: 20 kontur berjarak 3 mm, irisan dosis tiap 1,5 mm, dosis naik 0,4 Gy per mm. Untuk struktur kontinu, dosisnya seragam antara 19,4 dan 43,4 Gy, sehingga jawaban eksaknya bisa dihitung:

| | D95 | D2 | volume (cm³) |
|---|---|---|---|
| Eksak | 20,60 | 42,92 | 6,00 |
| Alatku (sebelum) | 20,60 | **43,40** | **6,15** |
| Alatku (sesudah) | 20,60 | 42,80 | 6,00 |
| dicompyler-core | 20,01 | 41,61 | 6,00 |

**Bug 1:** irisan dosis yang tepat di batas luar struktur terhitung penuh di kedua ujung, satu irisan kelebihan (volume +2,5%, D2 terlalu tinggi 0,48 Gy). Perbaikan: bobot tiap irisan = fraksi ketebalannya yang tercakup lempeng kontur.

Satu hal yang tidak boleh kulewatkan: dicompyler-core juga berbeda dari jawaban eksak, tapi karena **model** yang berbeda (ia mengambil sampel dosis hanya di bidang kontur dan tidak memperpanjang struktur melewati kontur ujung), bukan karena bug. Model ujung itu pilihan, dan jawaban "eksak" di atas berlaku untuk model lempeng.

## Run ketiga memperlihatkan bug kedua

Setelah perbaikan itu, selisih rata-rata dan D95 mengecil, tapi volume paru pasien 1 dan 2 sekarang **selalu negatif**: −1 sampai −9 cm³. Tanda yang konsisten berarti bias, bukan noise. Dugaanku: irisan dosis yang tepat di antara dua kontur kuberikan seluruhnya ke kontur yang lebih rendah.

Phantom kedua membuktikannya: sepuluh kontur dengan penampang yang membesar dari irisan ke irisan. Jumlah lempeng 6,060 cm³ dan dosis rata-rata berbobot 27,9485 Gy. Alatku memberi 5,709 cm³ (−5,8%) dan 28,0295 Gy. Perbaikan: irisan di batas dibagi sesuai tumpang tindih dengan tiap lempeng. Setelah itu volume dan rata-rata tepat sama dengan nilai analitik.

## Hasil akhir pada tiga pasien (39 struktur)

| Metrik | Run 1: melewati toleransi (selisih maks) | Run akhir |
|---|---|---|
| Dosis rata-rata | 9 (0,245 Gy) | 0 (0,028 Gy) |
| D50 | 5 (0,711 Gy) | 0 (0,034 Gy) |
| D2 | 4 (0,877 Gy) | 0 (0,095 Gy) |
| D95 | 5 (1,697 Gy) | 1 (1,112 Gy) |
| Volume | | selisih maks 0,0005 cm³ |

Sebagian besar selisih awal ternyata **bias di alatku sendiri**, bukan perbedaan model. Hipotesisku di tengah jalan ("sisa selisih kemungkinan perbedaan model") salah, dan data yang membantahnya.

# Ada juga kesalahan dalam asumsi yang kubuat sendiri

Selain dua bug tersebut, ada satu kesalahan lain yang cukup penting.

Aku sempat menganggap bahwa volume yang dilaporkan dicompyler-core berasal dari luas kontur dikalikan ketebalan irisan.

Berdasarkan asumsi itu, aku sempat mengubah skrip pembanding. Namun, setelah membaca kode sumber dicompyler-core, ternyata cara perhitungannya berbeda.

Pustaka tersebut menghitung jumlah piksel pada grid dosis yang berada di dalam kontur, kemudian mengalikannya dengan ketebalan irisan.

Artinya, volume yang dihasilkan memang berbasis sampling grid.

Aku akhirnya mengembalikan perubahan pada skrip pembanding tersebut.

Dari sini ada satu pelajaran sederhana yang cukup penting: jangan terlalu cepat menyimpulkan cara kerja sebuah library hanya berdasarkan nama metrik atau hasil keluarannya. Kalau memungkinkan, periksa langsung implementasinya.

## Beberapa hal yang kupelajari dari proses ini

Ada beberapa hal yang cukup berkesan selama proses pengujian ini.

1. **Phantom sederhana belum tentu cukup.** Phantom kubus yang kubuat sebelumnya lolos semua pengujian, tetapi tetap gagal mengungkap masalah ketika berhadapan dengan kontur organ yang lebih kompleks.
2. **Hasil pengujian perlu disertai informasi diagnostik.** Menampilkan angka saja tidak selalu membantu. Informasi seperti ukuran voxel dan jarak antaririsan justru membantu menemukan pola yang sebelumnya tidak terlihat.
3. **Phantom dengan jawaban analitik sangat membantu.** Membandingkan dua program hanya menunjukkan bahwa keduanya berbeda. Phantom dengan hasil yang sudah diketahui membantu menentukan implementasi mana yang bermasalah.
4. **Tes juga perlu diuji.** Aku mencoba memasukkan kesalahan secara sengaja ke dalam kode, seperti menukar dimensi baris dan kolom atau mengabaikan bobot perhitungan. Tujuannya untuk memastikan pengujian benar-benar bisa mendeteksi kesalahan. Dari sini aku menemukan beberapa tes yang ternyata selalu lulus karena kesalahan penulisan atribut DICOM dan satu asersi `or True`.
5. **Kesamaan hasil bukan jaminan kebenaran.** Dua program yang memberikan hasil serupa belum tentu benar. Begitu juga sebaliknya, hasil yang berbeda belum tentu menunjukkan adanya bug.

## Yang belum terbukti

Meskipun hasilnya sudah jauh lebih baik, masih ada beberapa keterbatasan yang perlu dicatat.

Pengujian ini baru menggunakan tiga pasien dari satu koleksi dataset dengan satu lokasi tumor. Aku juga belum membandingkan hasilnya dengan Treatment Planning System (TPS).

Masih ada satu struktur dengan selisih D95 sebesar 1,112 Gy yang belum berhasil kujelaskan. Selain itu, beberapa metrik V(t) masih menunjukkan perbedaan lebih dari 2%.

Nilai minimum dan maksimum dosis juga masih memiliki perbedaan sistematis karena implementasiku mengambil sampel pada lebih banyak irisan. Karena itu, kedua metrik tersebut belum kugunakan untuk menarik kesimpulan.

Jadi, meskipun hasil validasinya menunjukkan peningkatan yang cukup besar, **alat ini belum tervalidasi untuk penggunaan klinis dan tidak boleh digunakan sebagai dasar pengambilan keputusan klinis.**

## Sumber

- Dataset: Pancreatic-CT-CBCT-SEG, The Cancer Imaging Archive, CC BY 4.0. Hong, J., Reyngold, M., Crane, C., Cuaron, J., Hajj, C., Mann, J., Zinovoy, M., Yorke, E., LoCastro, E., Apte, A. P., & Mageras, G. (2021). Breath-hold CT and cone-beam CT images with expert manual organ-at-risk segmentations from radiation treatments of locally advanced pancreatic cancer [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.ESHQ-4D90
- Platform: Clark K, Vendt B, Smith K, et al. The Cancer Imaging Archive (TCIA): maintaining and operating a public information repository. J Digit Imaging 26(6), 1045-1057 (2013), https://doi.org/10.1007/s10278-013-9622-7.
- Tidak ada upaya mengidentifikasi atau menghubungi partisipan, dan tulisan ini hanya memuat angka agregat.
- Perbandingan: dicompyler-core 0.5.6.
