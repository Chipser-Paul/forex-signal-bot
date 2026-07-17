import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'firebase_options.dart';

const String kPrefsUrlKey = 'app_url';
const String kDefaultUrl = 'http://192.168.1.34:8501';
const AndroidNotificationChannel kTradeAlertsChannel = AndroidNotificationChannel(
  'trade_alerts',
  'Trade Alerts',
  description: 'Trade placed, exited, and target alerts',
  importance: Importance.max,
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ForexBotApp());
}

class ForexBotApp extends StatelessWidget {
  const ForexBotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Forex Signal Bot',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF070A12),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFF8D34F),
          secondary: Color(0xFF22D3EE),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0B1220),
          foregroundColor: Color(0xFFF8FAFC),
        ),
      ),
      home: const WebAppHome(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class WebAppHome extends StatefulWidget {
  const WebAppHome({super.key});

  @override
  State<WebAppHome> createState() => _WebAppHomeState();
}

class _WebAppHomeState extends State<WebAppHome> {
  WebViewController? _controller;
  String _currentUrl = '';
  bool _isLoading = true;
  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  bool _pushReady = false;
  String _pushStatus = 'Not configured';
  String _fcmToken = '';

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _loadUrlFromPrefs();
    await _setupPush();
  }

  Future<void> _loadUrlFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(kPrefsUrlKey) ?? kDefaultUrl;
    _setUrl(saved);
  }

  Future<void> _setupPush() async {
    try {
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      final messaging = FirebaseMessaging.instance;
      await _setupLocalNotifications();
      await messaging.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );
      final permission = await messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      final token = await messaging.getToken();
      if (!mounted) {
        return;
      }

      final allowed = permission.authorizationStatus == AuthorizationStatus.authorized ||
          permission.authorizationStatus == AuthorizationStatus.provisional;

      setState(() {
        _fcmToken = token ?? '';
        _pushReady = allowed && (token != null && token.isNotEmpty);
        if (!_pushReady) {
          _pushStatus = 'Permission denied or token unavailable';
        } else {
          _pushStatus = 'Ready';
        }
      });

      FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
        if (!mounted) {
          return;
        }
        setState(() {
          _fcmToken = newToken;
          _pushReady = newToken.isNotEmpty;
          _pushStatus = _pushReady ? 'Ready' : 'Token unavailable';
        });
      });

      FirebaseMessaging.onMessage.listen((message) {
        if (!mounted) {
          return;
        }
        final title = message.notification?.title ??
            message.data['title'] ??
            'Forex Signal Bot';
        final body = message.notification?.body ??
            message.data['body'] ??
            'New notification';
        _showForegroundNotification(title, body);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _pushReady = false;
        _pushStatus = 'Firebase not configured';
      });
    }
  }

  Future<void> _setupLocalNotifications() async {
    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: androidInit);
    await _localNotifications.initialize(settings);

    final androidPlugin = _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    if (androidPlugin != null) {
      await androidPlugin.createNotificationChannel(kTradeAlertsChannel);
      await androidPlugin.requestNotificationsPermission();
    }
  }

  Future<void> _showForegroundNotification(String title, String body) async {
    const details = NotificationDetails(
      android: AndroidNotificationDetails(
        kTradeAlertsChannel.id,
        kTradeAlertsChannel.name,
        channelDescription: kTradeAlertsChannel.description,
        importance: Importance.max,
        priority: Priority.high,
      ),
    );

    final notificationId = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    await _localNotifications.show(notificationId, title, body, details);
  }

  void _setUrl(String url) {
    final formatted = _normalizeUrl(url);
    if (formatted == null) {
      setState(() {
        _currentUrl = '';
      });
      return;
    }
    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) => setState(() => _isLoading = true),
          onPageFinished: (_) => setState(() => _isLoading = false),
        ),
      )
      ..loadRequest(Uri.parse(formatted));

    setState(() {
      _currentUrl = formatted;
      _controller = controller;
    });
  }

  String? _normalizeUrl(String url) {
    final trimmed = url.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return trimmed;
    }
    return 'http://$trimmed';
  }

  Future<void> _copyToken() async {
    if (_fcmToken.isEmpty) {
      return;
    }
    await Clipboard.setData(ClipboardData(text: _fcmToken));
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('FCM token copied')),
    );
  }

  Future<void> _openSettings() async {
    final controller = TextEditingController(text: _currentUrl.isEmpty ? kDefaultUrl : _currentUrl);
    final result = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: const Color(0xFF0B1220),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) {
        return SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
            16,
            20,
            16,
            24 + MediaQuery.of(context).viewInsets.bottom,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Connection URL',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: controller,
                decoration: const InputDecoration(
                  labelText: 'Streamlit URL',
                  hintText: 'https://your-tunnel.trycloudflare.com',
                ),
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () => Navigator.of(context).pop(controller.text),
                child: const Text('Save URL'),
              ),
              const SizedBox(height: 20),
              const Divider(),
              const SizedBox(height: 10),
              const Text(
                'Push Notifications (FCM)',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 6),
              Text('Status: $_pushStatus'),
              const SizedBox(height: 8),
              SelectableText(
                _fcmToken.isEmpty ? 'Token not available yet' : _fcmToken,
                style: const TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  ElevatedButton(
                    onPressed: _setupPush,
                    child: const Text('Refresh Token'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: _fcmToken.isEmpty ? null : _copyToken,
                    child: const Text('Copy Token'),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    if (result != null) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(kPrefsUrlKey, result);
      _setUrl(result);
    }
  }

  @override
  Widget build(BuildContext context) {
    final body = _currentUrl.isEmpty
        ? Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'Enter your Streamlit URL to continue.',
                    style: TextStyle(fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: _openSettings,
                    child: const Text('Set URL'),
                  ),
                ],
              ),
            ),
          )
        : Stack(
            children: [
              WebViewWidget(controller: _controller!),
              if (_isLoading)
                const Align(
                  alignment: Alignment.topCenter,
                  child: LinearProgressIndicator(minHeight: 3),
                ),
            ],
          );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Forex Signal Bot'),
        actions: [
          if (_pushReady)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Icon(Icons.notifications_active),
            ),
          IconButton(
            onPressed: () => _controller?.reload(),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            onPressed: _openSettings,
            icon: const Icon(Icons.settings),
          ),
        ],
      ),
      body: body,
    );
  }
}
