import 'package:flutter/foundation.dart';

class TutorialController {
  TutorialController._();

  static final ValueNotifier<int> requests = ValueNotifier<int>(0);

  static void start() {
    requests.value++;
  }
}
