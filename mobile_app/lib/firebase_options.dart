import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      default:
        return android;
    }
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyCSVgRQs_U7-O-ZLQDg6tnmQYN0rmKC66g',
    appId: '1:954001179455:android:954d13ac5a92ee8b7c098a',
    messagingSenderId: '954001179455',
    projectId: 'forex-signal-bot-1cd11',
    storageBucket: 'forex-signal-bot-1cd11.firebasestorage.app',
  );
}
