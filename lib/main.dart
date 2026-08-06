import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;

const String apiUrl =
    'https://safe-drive-demo.onrender.com/analyze-route';

void main() {
  runApp(const SafeDriveApp());
}

class SafeDriveApp extends StatelessWidget {
  const SafeDriveApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SAFE DRIVE',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1D4E89),
        ),
        scaffoldBackgroundColor: const Color(0xFFF6F8FB),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(
              color: Color(0xFFE1E6ED),
            ),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(
              color: Color(0xFF1D4E89),
              width: 2,
            ),
          ),
        ),
      ),
      home: const RouteInputScreen(),
    );
  }
}

class RouteInputScreen extends StatefulWidget {
  const RouteInputScreen({super.key});

  @override
  State<RouteInputScreen> createState() => _RouteInputScreenState();
}

class _RouteInputScreenState extends State<RouteInputScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _startController =
      TextEditingController(text: '서울역');
  final TextEditingController _destinationController =
      TextEditingController();

  TimeOfDay _departureTime = TimeOfDay.now();
  String _weather = '맑음';

  static const List<String> weatherOptions = [
    '맑음',
    '흐림',
    '비',
    '안개',
    '눈',
  ];

  @override
  void dispose() {
    _startController.dispose();
    _destinationController.dispose();
    super.dispose();
  }

  Future<void> _selectDepartureTime() async {
    final selectedTime = await showTimePicker(
      context: context,
      initialTime: _departureTime,
    );

    if (selectedTime != null && mounted) {
      setState(() {
        _departureTime = selectedTime;
      });
    }
  }

  void _analyzeRoute() {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => AnalysisLoadingScreen(
          startLocation: _startController.text.trim(),
          destination: _destinationController.text.trim(),
          departureTime: _departureTime,
          weather: _weather,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'SAFE DRIVE',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const SizedBox(height: 12),
              Container(
                width: 92,
                height: 92,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color(0xFFE5EFFA),
                ),
                child: const Icon(
                  Icons.shield_outlined,
                  size: 52,
                  color: Color(0xFF1D4E89),
                ),
              ),
              const SizedBox(height: 20),
              const Text(
                '안전 경로 분석',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '이동 경로와 시간대별 사고 특성을 분석하여\n안전운전 정보를 제공합니다.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.5,
                  color: Colors.black54,
                ),
              ),
              const SizedBox(height: 36),
              TextFormField(
                controller: _startController,
                decoration: const InputDecoration(
                  labelText: '출발지',
                  hintText: '예: 서울역',
                  prefixIcon: Icon(Icons.my_location),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return '출발지를 입력하세요.';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _destinationController,
                decoration: const InputDecoration(
                  labelText: '목적지',
                  hintText: '예: 용인시 기흥구',
                  prefixIcon: Icon(Icons.location_on_outlined),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return '목적지를 입력하세요.';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: _weather,
                decoration: const InputDecoration(
                  labelText: '현재 날씨',
                  prefixIcon: Icon(Icons.cloud_outlined),
                ),
                items: weatherOptions
                    .map(
                      (weather) => DropdownMenuItem(
                        value: weather,
                        child: Text(weather),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null) {
                    setState(() {
                      _weather = value;
                    });
                  }
                },
              ),
              const SizedBox(height: 16),
              InkWell(
                borderRadius: BorderRadius.circular(14),
                onTap: _selectDepartureTime,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 18,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: const Color(0xFFE1E6ED),
                    ),
                  ),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.schedule,
                        color: Color(0xFF1D4E89),
                      ),
                      const SizedBox(width: 14),
                      const Expanded(
                        child: Text(
                          '출발 예정 시간',
                          style: TextStyle(fontSize: 16),
                        ),
                      ),
                      Text(
                        _departureTime.format(context),
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 28),
              SizedBox(
                height: 54,
                child: FilledButton.icon(
                  onPressed: _analyzeRoute,
                  icon: const Icon(Icons.route),
                  label: const Text(
                    '안전 경로 분석',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                '과거 교통사고 자료와 실시간 교통정보를 기반으로 한 '
                '참고정보이며, 사고 발생을 예측하거나 보장하지 않습니다.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  height: 1.5,
                  color: Colors.black45,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AnalysisLoadingScreen extends StatefulWidget {
  const AnalysisLoadingScreen({
    super.key,
    required this.startLocation,
    required this.destination,
    required this.departureTime,
    required this.weather,
  });

  final String startLocation;
  final String destination;
  final TimeOfDay departureTime;
  final String weather;

  @override
  State<AnalysisLoadingScreen> createState() =>
      _AnalysisLoadingScreenState();
}

class _AnalysisLoadingScreenState extends State<AnalysisLoadingScreen> {
  @override
  void initState() {
    super.initState();
    _requestAnalysis();
  }

  Future<void> _requestAnalysis() async {
    try {
      final response = await http
          .post(
            Uri.parse(apiUrl),
            headers: const {
              'Content-Type': 'application/json; charset=UTF-8',
              'Accept': 'application/json',
            },
            body: jsonEncode({
              'origin': widget.startLocation,
              'destination': widget.destination,
              'weather': widget.weather,
            }),
          )
          .timeout(const Duration(seconds: 120));

      if (response.statusCode != 200) {
        String detail = response.body;
        try {
          final decoded = jsonDecode(utf8.decode(response.bodyBytes));
          if (decoded is Map<String, dynamic>) {
            detail = decoded['detail']?.toString() ?? detail;
          }
        } catch (_) {}

        throw Exception('서버 오류 ${response.statusCode}: $detail');
      }

      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('서버 응답 형식이 올바르지 않습니다.');
      }

      if (!mounted) {
        return;
      }

      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (context) => RouteResultScreen(
            startLocation: widget.startLocation,
            destination: widget.destination,
            departureTime: widget.departureTime,
            weather: widget.weather,
            result: decoded,
          ),
        ),
      );
    } on TimeoutException {
      if (!mounted) {
        return;
      }

      await _showAnalysisError(
        '서버 응답 시간이 초과되었습니다.\n\n'
        'Render 무료 서버가 시작 중이거나 분석에 시간이 걸릴 수 있습니다. '
        '잠시 후 다시 시도하세요.',
      );
    } on http.ClientException catch (error) {
      if (!mounted) {
        return;
      }

      await _showAnalysisError(
        '서버 연결에 실패했습니다.\n\n$error',
      );
    } on FormatException catch (error) {
      if (!mounted) {
        return;
      }

      await _showAnalysisError(
        '서버 응답을 해석하지 못했습니다.\n\n$error',
      );
    } catch (error) {
      if (!mounted) {
        return;
      }

      await _showAnalysisError(error.toString());
    }
  }

  Future<void> _showAnalysisError(String message) async {
    if (!mounted) {
      return;
    }

    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('경로 분석 실패'),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('확인'),
          ),
        ],
      ),
    );

    if (mounted) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 28),
                Text(
                  '경로의 사고 특성을 분석하고 있습니다.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 12),
                Text(
                  '경로, 통과 지역, 실시간 교통정보와\n사고 통계를 확인하고 있습니다.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    height: 1.5,
                    color: Colors.black54,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class RouteResultScreen extends StatelessWidget {
  const RouteResultScreen({
    super.key,
    required this.startLocation,
    required this.destination,
    required this.departureTime,
    required this.weather,
    required this.result,
  });

  final String startLocation;
  final String destination;
  final TimeOfDay departureTime;
  final String weather;
  final Map<String, dynamic> result;

  Map<String, dynamic> get summary =>
      _asStringMap(result['summary']);

  List<Map<String, dynamic>> get regions =>
      _asMapList(result['regions']);

  List<Map<String, dynamic>> get roadTypes =>
      _asMapList(result['road_types']);

  List<String> get messages =>
      _asStringList(result['messages']);

  @override
  Widget build(BuildContext context) {
    final distanceKm = _asDouble(summary['distance_km']);
    final durationMinutes = _asDouble(summary['duration_minutes']);
    final currentTimeBand =
        result['current_time_band']?.toString() ?? '-';

    return Scaffold(
      appBar: AppBar(
        title: const Text('경로 분석 결과'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Container(
            height: 190,
            decoration: BoxDecoration(
              color: const Color(0xFFDDE7F2),
              borderRadius: BorderRadius.circular(18),
            ),
            child: const Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.map_outlined,
                  size: 62,
                  color: Color(0xFF1D4E89),
                ),
                SizedBox(height: 12),
                Text(
                  '지도 및 이동 경로 표시 영역',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          _RouteSummaryCard(
            startLocation: startLocation,
            destination: destination,
            departureTime: departureTime,
            distanceKm: distanceKm,
            durationMinutes: durationMinutes,
            regionCount: regions.length,
            weather: weather,
            currentTimeBand: currentTimeBand,
          ),
          const SizedBox(height: 18),
          if (regions.isNotEmpty) ...[
            const _SectionTitle(title: '통과 지역'),
            ...regions.map(
              (region) => _RegionCard(region: region),
            ),
            const SizedBox(height: 8),
          ],
          if (roadTypes.isNotEmpty) ...[
            const _SectionTitle(title: '도로 구성'),
            _RoadTypeCard(roadTypes: roadTypes),
            const SizedBox(height: 18),
          ],
          const _SectionTitle(title: '안전운전 안내'),
          if (messages.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Text('표시할 안전운전 안내가 없습니다.'),
              ),
            )
          else
            ...messages.asMap().entries.map(
              (entry) => _MessageCard(
                number: entry.key + 1,
                message: entry.value,
              ),
            ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: messages.isEmpty
                ? null
                : () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) => DrivingModeScreen(
                          messages: messages,
                        ),
                      ),
                    );
                  },
            icon: const Icon(Icons.navigation),
            label: const Text('운전 시작'),
          ),
        ],
      ),
    );
  }
}

class _RouteSummaryCard extends StatelessWidget {
  const _RouteSummaryCard({
    required this.startLocation,
    required this.destination,
    required this.departureTime,
    required this.distanceKm,
    required this.durationMinutes,
    required this.regionCount,
    required this.weather,
    required this.currentTimeBand,
  });

  final String startLocation;
  final String destination;
  final TimeOfDay departureTime;
  final double distanceKm;
  final double durationMinutes;
  final int regionCount;
  final String weather;
  final String currentTimeBand;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '경로 요약',
              style: TextStyle(
                fontSize: 19,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 14),
            Text('$startLocation → $destination'),
            const SizedBox(height: 8),
            Text('출발 예정: ${departureTime.format(context)}'),
            const SizedBox(height: 8),
            Text('총 거리: ${distanceKm.toStringAsFixed(1)}km'),
            const SizedBox(height: 8),
            Text('예상 소요시간: ${durationMinutes.round()}분'),
            const SizedBox(height: 8),
            Text('통과 지역: $regionCount개'),
            const SizedBox(height: 8),
            Text('분석 조건: $weather · $currentTimeBand'),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 19,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

class _RegionCard extends StatelessWidget {
  const _RegionCard({required this.region});

  final Map<String, dynamic> region;

  @override
  Widget build(BuildContext context) {
    final sido = _firstValue(region, ['시도', 'sido']);
    final sigungu = _firstValue(
      region,
      ['시군구', '시군구명', 'sigungu'],
    );
    final detailAddress = _firstValue(
      region,
      ['전체주소', '주소', 'address'],
    );
    final eta = _firstValue(
      region,
      ['eta_minutes', '진입예상분'],
    );
    final duration = _firstValue(
      region,
      ['duration_minutes', '통과시간분'],
    );
    final trafficStatus = _firstValue(
      region,
      ['traffic_status', '혼잡상태', '교통상태'],
    );
    final averageSpeed = _firstValue(
      region,
      ['average_speed', '평균속도'],
    );

    final titleParts = <String>[
      if (sido.isNotEmpty) sido,
      if (sigungu.isNotEmpty && sigungu != sido) sigungu,
    ];

    final title = titleParts.isNotEmpty
        ? titleParts.join(' ')
        : detailAddress.isNotEmpty
            ? detailAddress
            : '통과 지역';

    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.bold,
              ),
            ),
            if (detailAddress.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                detailAddress,
                style: const TextStyle(color: Colors.black54),
              ),
            ],
            if (eta.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('진입 예상: 약 ${_formatNumberText(eta)}분 후'),
            ],
            if (duration.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('예상 통과시간: 약 ${_formatNumberText(duration)}분'),
            ],
            if (trafficStatus.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('현재 교통상태: $trafficStatus'),
            ],
            if (averageSpeed.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('평균속도: ${_formatNumberText(averageSpeed)}km/h'),
            ],
          ],
        ),
      ),
    );
  }
}

class _RoadTypeCard extends StatelessWidget {
  const _RoadTypeCard({required this.roadTypes});

  final List<Map<String, dynamic>> roadTypes;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: roadTypes.map((item) {
            final name = _firstValue(
              item,
              ['도로종류', 'road_type', 'name'],
            );
            final ratio = _firstValue(
              item,
              ['비율', '비중', 'ratio', 'percentage'],
            );
            final distance = _firstValue(
              item,
              ['거리_km', '거리', 'distance_km'],
            );

            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: [
                  Expanded(
                    child: Text(name.isEmpty ? '기타' : name),
                  ),
                  if (distance.isNotEmpty)
                    Text('${_formatNumberText(distance)}km'),
                  if (ratio.isNotEmpty) ...[
                    const SizedBox(width: 10),
                    Text('${_formatNumberText(ratio)}%'),
                  ],
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }
}

class _MessageCard extends StatelessWidget {
  const _MessageCard({
    required this.number,
    required this.message,
  });

  final int number;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CircleAvatar(
              radius: 15,
              child: Text(
                '$number',
                style: const TextStyle(fontSize: 12),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  fontSize: 16,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DrivingModeScreen extends StatefulWidget {
  const DrivingModeScreen({
    super.key,
    required this.messages,
  });

  final List<String> messages;

  @override
  State<DrivingModeScreen> createState() =>
      _DrivingModeScreenState();
}

class _DrivingModeScreenState extends State<DrivingModeScreen> {
  final FlutterTts _flutterTts = FlutterTts();
  int _currentMessageIndex = 0;
  bool _isSpeaking = false;

  @override
  void initState() {
    super.initState();
    _configureTts();
  }

  Future<void> _configureTts() async {
    await _flutterTts.setLanguage('ko-KR');
    await _flutterTts.setSpeechRate(0.45);
    await _flutterTts.setVolume(1.0);
    await _flutterTts.setPitch(1.0);
    await _flutterTts.awaitSpeakCompletion(true);

    _flutterTts.setStartHandler(() {
      if (mounted) {
        setState(() {
          _isSpeaking = true;
        });
      }
    });

    _flutterTts.setCompletionHandler(() {
      if (mounted) {
        setState(() {
          _isSpeaking = false;
        });
      }
    });

    _flutterTts.setErrorHandler((_) {
      if (mounted) {
        setState(() {
          _isSpeaking = false;
        });
      }
    });

    await _speakCurrentMessage();
  }

  Future<void> _speakCurrentMessage() async {
    if (widget.messages.isEmpty) {
      return;
    }

    await _flutterTts.stop();
    await _flutterTts.speak(
      widget.messages[_currentMessageIndex],
    );
  }

  Future<void> _speakAllMessages() async {
    if (widget.messages.isEmpty) {
      return;
    }

    await _flutterTts.stop();
    await _flutterTts.speak(widget.messages.join(' '));
  }

  void _showPreviousMessage() {
    if (_currentMessageIndex == 0) {
      return;
    }

    setState(() {
      _currentMessageIndex--;
    });
    _speakCurrentMessage();
  }

  void _showNextMessage() {
    if (_currentMessageIndex >= widget.messages.length - 1) {
      return;
    }

    setState(() {
      _currentMessageIndex++;
    });
    _speakCurrentMessage();
  }

  @override
  void dispose() {
    _flutterTts.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final message = widget.messages.isEmpty
        ? '안내 문장이 없습니다.'
        : widget.messages[_currentMessageIndex];

    return Scaffold(
      backgroundColor: const Color(0xFF101820),
      appBar: AppBar(
        title: const Text('운전 중 안내'),
        backgroundColor: const Color(0xFF101820),
        foregroundColor: Colors.white,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                _isSpeaking
                    ? Icons.volume_up_rounded
                    : Icons.warning_amber_rounded,
                size: 92,
                color: Colors.amber,
              ),
              const SizedBox(height: 28),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  height: 1.45,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                widget.messages.isEmpty
                    ? '0 / 0'
                    : '${_currentMessageIndex + 1} / '
                        '${widget.messages.length}',
                style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 16,
                ),
              ),
              const SizedBox(height: 32),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton.filledTonal(
                    onPressed: _currentMessageIndex > 0
                        ? _showPreviousMessage
                        : null,
                    icon: const Icon(Icons.skip_previous),
                    tooltip: '이전 안내',
                  ),
                  const SizedBox(width: 14),
                  FilledButton.icon(
                    onPressed: _speakCurrentMessage,
                    icon: const Icon(Icons.volume_up),
                    label: const Text('다시 듣기'),
                  ),
                  const SizedBox(width: 14),
                  IconButton.filledTonal(
                    onPressed:
                        _currentMessageIndex < widget.messages.length - 1
                            ? _showNextMessage
                            : null,
                    icon: const Icon(Icons.skip_next),
                    tooltip: '다음 안내',
                  ),
                ],
              ),
              const SizedBox(height: 14),
              TextButton.icon(
                onPressed:
                    widget.messages.isEmpty ? null : _speakAllMessages,
                icon: const Icon(Icons.playlist_play),
                label: const Text('전체 안내 듣기'),
                style: TextButton.styleFrom(
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Map<String, dynamic> _asStringMap(dynamic value) {
  if (value is Map<String, dynamic>) {
    return value;
  }

  if (value is Map) {
    return value.map(
      (key, item) => MapEntry(key.toString(), item),
    );
  }

  return <String, dynamic>{};
}

List<Map<String, dynamic>> _asMapList(dynamic value) {
  if (value is! List) {
    return <Map<String, dynamic>>[];
  }

  return value
      .map(_asStringMap)
      .where((item) => item.isNotEmpty)
      .toList();
}

List<String> _asStringList(dynamic value) {
  if (value is! List) {
    return <String>[];
  }

  return value
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList();
}

double _asDouble(dynamic value) {
  if (value is num) {
    return value.toDouble();
  }

  return double.tryParse(value?.toString() ?? '') ?? 0;
}

String _firstValue(
  Map<String, dynamic> map,
  List<String> keys,
) {
  for (final key in keys) {
    final value = map[key];
    if (value != null && value.toString().trim().isNotEmpty) {
      return value.toString().trim();
    }
  }

  return '';
}

String _formatNumberText(String value) {
  final number = double.tryParse(value);
  if (number == null) {
    return value;
  }

  if (number == number.roundToDouble()) {
    return number.round().toString();
  }

  return number.toStringAsFixed(1);
}
