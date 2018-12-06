# How to install the Notsobot cog
**Requirements for Python**
`pip3 install python-aalib imgurpython pyfiglet numpy pillow lxml`
`pip3 install git+https://github.com/Kareeeeem/jpglitch`
**Note: python-aalib uses ctypes to access aalib. As a result aalib is not available on Mac OS systems and will not import. You can still use everything except the ascii art commands.**


**Requirements for ImageMagick**
https://imagemagick.org/script/download.php
http://docs.wand-py.org/en/0.4.4/guide/install.html#

Install the latest source in Ubuntu with:
`sudo apt-get install libmagickwand-dev, libaa1-dev`
https://linuxconfig.org/how-to-install-imagemagick-7-on-ubuntu-18-04-linux


`wget ftp://ftp.imagemagick.org/pub/ImageMagick/ImageMagick.tar.gz
tar xvfz ImageMagick.tar.gz
cd ImageMagick-*
./configure --disable-shared
make
sudo make install`

