import 'dart:typed_data';
import 'package:share_plus/share_plus.dart';

Future<void> saveBytes(Uint8List bytes, String fileName) async {
  final xFile = XFile.fromData(
    bytes,
    name: fileName,
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  );
  await Share.shareXFiles([xFile], text: 'FinTrack — финансовый отчёт');
}
