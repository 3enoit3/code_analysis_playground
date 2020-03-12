DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
JSON=compile_commands.json
SOURCE=example.c

rm -f $DIR/$JSON
echo "
[
{
  \"directory\": \"$DIR\",
  \"command\": \"/usr/bin/c++ -I/usr/include -std=c++1y -o $DIR/$SOURCE.o -c $DIR/$SOURCE\",
  \"file\": \"$DIR/$SOURCE\"
}
]" > $DIR/$JSON
