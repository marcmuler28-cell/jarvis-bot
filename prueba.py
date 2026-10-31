Script iniciado en 2026-06-10 22:41:41-05:00 [TERM="xterm-256color" TTY="/dev/pts/1" COLUMNS="236" LINES="63"]
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit[27m[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[Cpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit
[?2004l]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mpactl list sources short | grep bluez[27m[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[Cpactl list sources short | grep bluez
[?2004l104	[01;31m[Kbluez[m[K_input.A8:E6:E8:5F:1F:3A	PipeWire	float32le 1ch 48000Hz	SUSPENDED
1198	[01;31m[Kbluez[m[K_output.A8_E6_E8_5F_1F_3A.1.monitor	PipeWire	s16le 1ch 16000Hz	SUSPENDED
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit[27m[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[Cpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit
[?2004l]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mparecord --device=bluez_input.A8:E6:E8:5F:1F:3A --format=s16le --rate=16000 --channels=1 --file-format=wav /tmp/test.wav --time=3[27m[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[C[Cparecord --device=bluez_input.A8:E6:E8:5F:1F:3A --format=s16le --rate=16000 --channels=1 --file-format=wav /tmp/test.wav --time=3
[?2004lparecord: unrecognized option '--time=3'
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7maplay /tmp/test.wav[27maplay /tmp/test.wav
[?2004l/tmp/test.wav: No existe el fichero o el directorio
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit[27m
[7mtimeout 3 parecord --device=bluez_input.A8:E6:E8:5F:1F:3A --format=s16le --rate=16000 --channels=1 --file-format=wav /tmp/test.wav[27m
[7maplay /tmp/test.wav[27m[A[A[C[C[C[C[C[C[C[C[C[C[Cpactl set-card-profile bluez_card.A8_E6_E8_5F_1F_3A headset-head-unit
timeout 3 parecord --device=bluez_input.A8:E6:E8:5F:1F:3A --format=s16le --rate=16000 --channels=1 --file-format=wav /tmp/test.wav
aplay /tmp/test.wav
[?2004lPlaying WAVE '/tmp/test.wav' : Signed 16 bit Little Endian, Rate 16000 Hz, Mono
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mls -lh /tmp/test.wav[27mls -lh /tmp/test.wav
[?2004l-rw-r--r-- 1 marc marc 63K jun 10 22:45 /tmp/test.wav
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7maplay /tmp/test.wav[27maplay /tmp/test.wav
[?2004lPlaying WAVE '/tmp/test.wav' : Signed 16 bit Little Endian, Rate 16000 Hz, Mono
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7marecord -l[27marecord -l
[?2004l**** List of CAPTURE Hardware Devices ****
card 1: Generic_1 [HD-Audio Generic], device 0: ALC897 Analog [ALC897 Analog]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: Generic_1 [HD-Audio Generic], device 2: ALC897 Alt Analog [ALC897 Alt Analog]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
]0;marc@marc-ms7c95:~/Descargas/JarvisBot[?2004h[marc@marc-ms7c95 JarvisBot]$ [7mpavucontrol[27mpavucontrol
[?2004l
(pavucontrol:11072): Gtk-[1;33mWARNING[0m **: [34m22:48:28.760[0m: GtkGizmo 0x598535691260 (slider) reported min width -2, but sizes must be >= 0

(pavucontrol:11072): Gtk-[1;33mWARNING[0m **: [34m22:48:28.760[0m: GtkGizmo 0x59853546f050 (slider) reported min height -2, but sizes must be >= 0

(pavucontrol:11072): Gtk-[1;33mWARNING[0m **: [34m22:48:31.963[0m: GtkGizmo 0x5985358ca120 (slider) reported min width -2, but sizes m