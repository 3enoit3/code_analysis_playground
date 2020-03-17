Q3=Quake-III-Arena
rm -rf $Q3
git clone https://github.com/id-Software/Quake-III-Arena

cp ./scripts/nothing $Q3
cp ./scripts/capture $Q3

cd $Q3
rm -f compile_commands.json

ln -s capture gcc
ln -s nothing cc
ln -s nothing g++
ln -s nothing nasm
ln -s nothing ar
ln -s nothing q3lcc
ln -s nothing q3asm
export PATH=`pwd`:$PATH

cd code
perl ./unix/cons -k
