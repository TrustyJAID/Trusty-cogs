# How to install the NotSoBot cog
**Requirements for Python**
```
pip3 install python-aalib pyfiglet numpy pillow wand
pip3 install git+https://github.com/Kareeeeem/jpglitch
```
**Note for Mac users: python-aalib uses ctypes to access aalib. As a result aalib is not available on Mac OS systems and will not import. You can still use everything except the ascii art commands.**


**Requirements for ImageMagick**
* https://imagemagick.org/script/download.php
* http://docs.wand-py.org/en/0.6.4/guide/install.html

```
sudo apt -y install libncurses5-dev libbz2-dev libpng-dev libffi-dev libssl-dev liblzma-dev tk-dev libfreetype6-dev libdb5.3-dev libsqlite3-dev libncursesw5-dev libmagickwand-dev git libgdbm-dev imagemagick zlib1g-dev build-essential unzip libexpat1-dev libjpeg-dev ffmpeg libreadline6-dev webp libaa1-dev
```

Install the latest version of ImageMagick from source in Ubuntu/Debian based systems with:
* https://linuxconfig.org/how-to-install-imagemagick-7-on-ubuntu-18-04-linux



# If the above does not work here's how you can install from source on Ubuntu

```bash
wget https://www.imagemagick.org/download/ImageMagick.tar.gz
tar xvfz ImageMagick.tar.gz
cd ImageMagick-*
./configure --disable-shared
make -j "$(nproc)"
sudo make install
```

## Installing ImageMagick on Windows
These instructions are specifically for installing ImageMagick for bots hosted on windows computers.

1. Go to [this link](https://imagemagick.org/script/download.php#windows) and click the first link on that page to begin downloading ImageMagick.

2. When the download finishes, run the downloaded file and click `accept` on the "License Agreement".

3. Click `next` on the "Information" screen.

4. The default install location should be something like `C:\Program Files\ImageMagick-6.9.11`. **Remember what it is set to.** It will be needed for a later step. You might want to copy it somewhere so you can remember it. When you are ready, click `next`.

5. Click `next` on the "Select Start Menu Folder" screen.

6. In the "Select Additional Tasks" screen, ensure that the following 3 options are checked:
- Add application directory to your system path
- Install FFmpeg
- Install development headers and libraries for C and C++
then click `next`.

7. Click `install` to begin the installation.

8. When the installation finishes, click `next` and then `finish`.

9. Head to `<datapath>\cogs\Downloader\lib\moviepy`, replacing `<datapath>` with your bot's data path. Your data path can be found by running the command `[p]datapath`.

10. Shut down your bot.

11. Open the file `config_defaults.py`.

12. Replace the last line in that file `IMAGEMAGICK_BINARY = os.getenv('IMAGEMAGICK_BINARY', 'auto-detect')` with `IMAGEMAGICK_BINARY = r"<INSTALL_LOCATION>\convert.exe"`, replacing `<INSTALL_LOCATION>` with the install location from step 4.

13. Save and close the file.

14. Start up your bot. `[p]crabrave` should now be working.
