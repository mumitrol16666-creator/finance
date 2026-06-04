import 'dart:typed_data';
import 'file_saver_stub.dart'
    if (dart.library.html) 'file_saver_web.dart'
    if (dart.library.io) 'file_saver_mobile.dart';

abstract class FileSaver {
  static Future<void> saveFile(Uint8List bytes, String fileName) async {
    await saveBytes(bytes, fileName);
  }
}
