import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

const String apiBaseUrl = 'http://127.0.0.1:8000';

const String analyzeRouteUrl = '$apiBaseUrl/analyze-route';
const String startDrivingUrl = '$apiBaseUrl/start-driving';
const String updateLocationUrl = '$apiBaseUrl/update-location';
const String drivingStatusUrl = '$apiBaseUrl/driving-status';
const String stopDrivingUrl = '$apiBaseUrl/stop-driving';

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
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1D4E89)),
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
            borderSide: const BorderSide(color: Color(0xFFE1E6ED)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: Color(0xFF1D4E89), width: 2),
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
  final TextEditingController _startController = TextEditingController(
    text: '서울역',
  );
  final TextEditingController _destinationController = TextEditingController();

  Position? _currentPosition;
  bool _useCurrentLocation = false;
  bool _isLoadingStartLocation = false;

  TimeOfDay _departureTime = TimeOfDay.now();
  String _weather = '맑음';

  static const List<String> weatherOptions = ['맑음', '흐림', '비', '안개', '눈'];

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

  Future<void> _selectCurrentLocation() async {
    setState(() {
      _isLoadingStartLocation = true;
    });

    try {
      final position = await determineCurrentPosition();

      if (!mounted) {
        return;
      }

      setState(() {
        _currentPosition = position;
        _useCurrentLocation = true;
        _startController.text = '현재 위치';
        _isLoadingStartLocation = false;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('현재 위치를 출발지로 설정했습니다.')));
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isLoadingStartLocation = false;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('현재 위치를 가져오지 못했습니다.\n$error')));
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
          originLatitude: _useCurrentLocation
              ? _currentPosition?.latitude
              : null,
          originLongitude: _useCurrentLocation
              ? _currentPosition?.longitude
              : null,
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
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
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
                decoration: InputDecoration(
                  labelText: '출발지',
                  hintText: '예: 서울역',
                  prefixIcon: const Icon(Icons.my_location),
                  suffixIcon: _useCurrentLocation
                      ? const Icon(Icons.gps_fixed, color: Colors.green)
                      : null,
                ),
                onChanged: (_) {
                  if (_useCurrentLocation) {
                    setState(() {
                      _useCurrentLocation = false;
                      _currentPosition = null;
                    });
                  }
                },
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return '출발지를 입력하세요.';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: _isLoadingStartLocation
                      ? null
                      : _selectCurrentLocation,
                  icon: _isLoadingStartLocation
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.gps_fixed),
                  label: Text(
                    _isLoadingStartLocation ? '현재 위치 확인 중' : '현재 위치 사용',
                  ),
                ),
              ),
              const SizedBox(height: 8),
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
                    border: Border.all(color: const Color(0xFFE1E6ED)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.schedule, color: Color(0xFF1D4E89)),
                      const SizedBox(width: 14),
                      const Expanded(
                        child: Text('출발 예정 시간', style: TextStyle(fontSize: 16)),
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
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
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
    this.originLatitude,
    this.originLongitude,
  });

  final String startLocation;
  final String destination;
  final TimeOfDay departureTime;
  final String weather;
  final double? originLatitude;
  final double? originLongitude;

  @override
  State<AnalysisLoadingScreen> createState() => _AnalysisLoadingScreenState();
}

class _AnalysisLoadingScreenState extends State<AnalysisLoadingScreen> {
  @override
  void initState() {
    super.initState();
    _requestAnalysis();
  }

  Future<void> _requestAnalysis() async {
    try {
      final requestBody = <String, dynamic>{
        'origin': widget.startLocation,
        'destination': widget.destination,
        'weather': widget.weather,
      };

      if (widget.originLatitude != null && widget.originLongitude != null) {
        requestBody['origin_latitude'] = widget.originLatitude;
        requestBody['origin_longitude'] = widget.originLongitude;
      }

      final response = await http
          .post(
            Uri.parse(analyzeRouteUrl),
            headers: const {'Content-Type': 'application/json; charset=UTF-8'},
            body: jsonEncode(requestBody),
          )
          .timeout(const Duration(seconds: 180));

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
    } catch (error) {
      if (!mounted) {
        return;
      }

      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('경로 분석 실패'),
          content: Text('$error\n\nFastAPI 서버가 실행 중인지 확인하세요.'),
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
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
                SizedBox(height: 12),
                Text(
                  '경로, 통과 지역, 실시간 교통정보와\n사고 통계를 확인하고 있습니다.',
                  textAlign: TextAlign.center,
                  style: TextStyle(height: 1.5, color: Colors.black54),
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

  Map<String, dynamic> get summary => _asStringMap(result['summary']);

  List<Map<String, dynamic>> get regions => _asMapList(result['regions']);

  List<Map<String, dynamic>> get roadTypes => _asMapList(result['road_types']);

  List<String> get messages => _asStringList(result['messages']);

  List<LatLng> get routePoints {
    final rawPoints = result['route_points'];

    if (rawPoints is! List) {
      return <LatLng>[];
    }

    return rawPoints
        .map(_asStringMap)
        .where(
          (point) =>
              point.containsKey('latitude') && point.containsKey('longitude'),
        )
        .map(
          (point) => LatLng(
            _asDouble(point['latitude']),
            _asDouble(point['longitude']),
          ),
        )
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final distanceKm = _asDouble(summary['distance_km']);
    final durationMinutes = _asDouble(summary['duration_minutes']);
    final currentTimeBand = result['current_time_band']?.toString() ?? '-';

    return Scaffold(
      appBar: AppBar(title: const Text('경로 분석 결과')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          RouteMapView(routePoints: routePoints),
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
            ...regions.map((region) => _RegionCard(region: region)),
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
              (entry) =>
                  _MessageCard(number: entry.key + 1, message: entry.value),
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
                          initialMessages: messages,
                          routePoints: routePoints,
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

class RouteMapView extends StatefulWidget {
  const RouteMapView({super.key, required this.routePoints});

  final List<LatLng> routePoints;

  @override
  State<RouteMapView> createState() => _RouteMapViewState();
}

class _RouteMapViewState extends State<RouteMapView> {
  LatLng? _currentLocation;
  String? _locationError;
  bool _isLoadingLocation = true;

  @override
  void initState() {
    super.initState();
    _loadCurrentLocation();
  }

  Future<void> _loadCurrentLocation() async {
    try {
      final position = await determineCurrentPosition();

      if (!mounted) {
        return;
      }

      setState(() {
        _currentLocation = LatLng(position.latitude, position.longitude);
        _locationError = null;
        _isLoadingLocation = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _locationError = error.toString();
        _isLoadingLocation = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final routePoints = widget.routePoints;

    if (routePoints.length < 2) {
      return Container(
        height: 280,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: const Color(0xFFDDE7F2),
          borderRadius: BorderRadius.circular(18),
        ),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.map_outlined, size: 56, color: Color(0xFF1D4E89)),
            SizedBox(height: 12),
            Text(
              '표시할 경로 좌표가 없습니다.',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ],
        ),
      );
    }

    final boundsPoints = <LatLng>[...routePoints, ?_currentLocation];
    final bounds = LatLngBounds.fromPoints(boundsPoints);

    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: SizedBox(
        height: 300,
        child: Stack(
          children: [
            FlutterMap(
              options: MapOptions(
                initialCameraFit: CameraFit.bounds(
                  bounds: bounds,
                  padding: const EdgeInsets.all(36),
                ),
              ),
              children: [
                TileLayer(
                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.example.safe_drive',
                ),
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: routePoints,
                      strokeWidth: 5,
                      color: const Color(0xFF1D4E89),
                    ),
                  ],
                ),
                MarkerLayer(
                  markers: [
                    Marker(
                      point: routePoints.first,
                      width: 48,
                      height: 48,
                      child: const Icon(
                        Icons.trip_origin,
                        size: 34,
                        color: Colors.green,
                      ),
                    ),
                    Marker(
                      point: routePoints.last,
                      width: 48,
                      height: 48,
                      child: const Icon(
                        Icons.location_on,
                        size: 42,
                        color: Colors.red,
                      ),
                    ),
                    if (_currentLocation != null)
                      Marker(
                        point: _currentLocation!,
                        width: 52,
                        height: 52,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.blue.withValues(alpha: 0.20),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.my_location,
                            size: 32,
                            color: Colors.blue,
                          ),
                        ),
                      ),
                  ],
                ),
                RichAttributionWidget(
                  attributions: const [
                    TextSourceAttribution('OpenStreetMap contributors'),
                  ],
                ),
              ],
            ),
            if (_isLoadingLocation)
              const Positioned(
                top: 12,
                right: 12,
                child: Card(
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        SizedBox(width: 8),
                        Text('현재 위치 확인 중'),
                      ],
                    ),
                  ),
                ),
              ),
            if (_locationError != null)
              Positioned(
                top: 12,
                left: 12,
                right: 12,
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: Row(
                      children: [
                        const Expanded(
                          child: Text(
                            '현재 위치를 불러오지 못했습니다.',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        IconButton(
                          onPressed: () {
                            setState(() {
                              _isLoadingLocation = true;
                              _locationError = null;
                            });
                            _loadCurrentLocation();
                          },
                          icon: const Icon(Icons.refresh),
                          tooltip: '현재 위치 다시 확인',
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
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
              style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
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
        style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
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
    final sigungu = _firstValue(region, ['시군구', '시군구명', 'sigungu']);
    final detailAddress = _firstValue(region, ['전체주소', '주소', 'address']);
    final eta = _firstValue(region, ['eta_minutes', '진입예상분']);
    final duration = _firstValue(region, ['duration_minutes', '통과시간분']);
    final trafficStatus = _firstValue(region, [
      'traffic_status',
      '혼잡상태',
      '교통상태',
    ]);
    final averageSpeed = _firstValue(region, ['average_speed', '평균속도']);

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
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
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
            final name = _firstValue(item, ['도로종류', 'road_type', 'name']);
            final ratio = _firstValue(item, [
              '비율',
              '비중',
              'ratio',
              'percentage',
            ]);
            final distance = _firstValue(item, ['거리_km', '거리', 'distance_km']);

            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: [
                  Expanded(child: Text(name.isEmpty ? '기타' : name)),
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
  const _MessageCard({required this.number, required this.message});

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
              child: Text('$number', style: const TextStyle(fontSize: 12)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(fontSize: 16, height: 1.5),
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
    required this.initialMessages,
    required this.routePoints,
  });

  final List<String> initialMessages;
  final List<LatLng> routePoints;

  @override
  State<DrivingModeScreen> createState() => _DrivingModeScreenState();
}

class _DrivingModeScreenState extends State<DrivingModeScreen> {
  final FlutterTts _flutterTts = FlutterTts();
  final MapController _mapController = MapController();

  StreamSubscription<Position>? _positionSubscription;

  List<String> _messages = [];
  Position? _currentPosition;
  Map<String, dynamic>? _currentRegion;

  int _currentMessageIndex = 0;

  double _routeProgressKm = 0;
  double _distanceFromRouteM = 0;
  double _remainingDistanceKm = 0;
  double _remainingMinutes = 0;
  double _currentSpeedKmh = 0;
  double _continuousDrivingMinutes = 0;

  String _currentWeather = '확인 중';
  String _weatherSource = '초기 설정';

  bool _isSpeaking = false;
  bool _isDriving = false;
  bool _isStartingDriving = true;
  bool _isSendingLocation = false;
  bool _isStoppingDriving = false;
  bool _isResting = false;
  bool _restAlert = false;

  String? _lastSpokenMessage;
  String? _drivingError;

  @override
  void initState() {
    super.initState();

    _messages = List<String>.from(widget.initialMessages);

    _configureTts();
    _startDriving();
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
  }

  Future<void> _startDriving() async {
    try {
      final response = await http
          .post(
            Uri.parse(startDrivingUrl),
            headers: const {'Content-Type': 'application/json; charset=UTF-8'},
            body: jsonEncode({
              'refresh_seconds': 300,
              'rest_confirm_seconds': 600,
              'rest_alert_seconds': 3600,
            }),
          )
          .timeout(const Duration(seconds: 30));

      if (response.statusCode != 200) {
        throw Exception(
          _extractServerError(response, fallback: '운전 시작에 실패했습니다.'),
        );
      }

      if (!mounted) {
        return;
      }

      setState(() {
        _isDriving = true;
        _isStartingDriving = false;
        _drivingError = null;
      });

      await _startLocationStream();
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isStartingDriving = false;
        _drivingError = error.toString();
      });
    }
  }

  Future<void> _startLocationStream() async {
    final firstPosition = await determineCurrentPosition();

    if (!mounted || !_isDriving) {
      return;
    }

    await _sendLocationUpdate(firstPosition);

    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 10,
    );

    await _positionSubscription?.cancel();

    _positionSubscription =
        Geolocator.getPositionStream(locationSettings: locationSettings).listen(
          (position) {
            _sendLocationUpdate(position);
          },
          onError: (Object error) {
            if (!mounted) {
              return;
            }

            setState(() {
              _drivingError = 'GPS 위치를 수신하지 못했습니다: $error';
            });
          },
        );
  }

  Future<void> _sendLocationUpdate(
    Position position, {
    bool forceRefresh = false,
  }) async {
    if (!_isDriving || _isSendingLocation) {
      return;
    }

    _isSendingLocation = true;

    try {
      final speedKmh = position.speed.isFinite && position.speed > 0
          ? position.speed * 3.6
          : 0.0;

      final response = await http
          .post(
            Uri.parse(updateLocationUrl),
            headers: const {'Content-Type': 'application/json; charset=UTF-8'},
            body: jsonEncode({
              'latitude': position.latitude,
              'longitude': position.longitude,
              'speed_kmh': speedKmh,
              'force_refresh': forceRefresh,
            }),
          )
          .timeout(const Duration(seconds: 180));

      if (response.statusCode != 200) {
        throw Exception(
          _extractServerError(response, fallback: '현재 위치 갱신에 실패했습니다.'),
        );
      }

      final decoded = jsonDecode(utf8.decode(response.bodyBytes));

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('위치 갱신 응답 형식이 올바르지 않습니다.');
      }

      _applyDrivingStatus(
        data: decoded,
        position: position,
        speedKmh: speedKmh,
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _drivingError = error.toString();
        });
      }
    } finally {
      _isSendingLocation = false;
    }
  }

  void _applyDrivingStatus({
    required Map<String, dynamic> data,
    required Position position,
    required double speedKmh,
  }) {
    final progress = _asStringMap(data['progress']);
    final region = _asStringMap(data['region']);
    final newMessages = _asStringList(data['messages']);
    final environment = _asStringMap(data['environment']);

    final weather = data['weather']?.toString().trim() ?? '';
    final weatherSource =
        environment['weather_source']?.toString().trim() ?? '';

    if (!mounted) {
      return;
    }

    setState(() {
      _currentPosition = position;
      _currentSpeedKmh = speedKmh;
      _currentRegion = region.isEmpty ? null : region;

      if (weather.isNotEmpty) {
        _currentWeather = weather;
      }

      if (weatherSource == 'api') {
        _weatherSource = '실시간 API';
      } else if (weatherSource == 'previous') {
        _weatherSource = '이전 날씨 유지';
      } else if (weatherSource.isNotEmpty) {
        _weatherSource = weatherSource;
      }

      _routeProgressKm = _asDouble(progress['route_progress_km']);
      _distanceFromRouteM = _asDouble(progress['distance_from_route_m']);
      _remainingDistanceKm = _asDouble(progress['remaining_distance_km']);
      _remainingMinutes = _asDouble(progress['remaining_minutes']);
      _continuousDrivingMinutes = _asDouble(data['continuous_driving_minutes']);

      _isResting = data['is_resting'] == true;
      _restAlert = data['rest_alert'] == true;

      if (newMessages.isNotEmpty) {
        _messages = newMessages;
        _currentMessageIndex = 0;
      }

      _drivingError = null;
    });

    try {
      _mapController.move(LatLng(position.latitude, position.longitude), 16);
    } catch (_) {
      // 지도가 아직 생성되기 전이면 이동 명령을 생략합니다.
    }

    if (newMessages.isNotEmpty) {
      _speakNewMessage(newMessages.first);
    } else if (_restAlert) {
      _speakNewMessage('연속 운전시간이 길어졌습니다. 안전한 장소에서 휴식하세요.');
    }
  }

  Future<void> _speakNewMessage(String message) async {
    final normalized = message.trim();

    if (normalized.isEmpty || normalized == _lastSpokenMessage) {
      return;
    }

    _lastSpokenMessage = normalized;

    await _flutterTts.stop();
    await _flutterTts.speak(normalized);
  }

  Future<void> _speakCurrentMessage() async {
    if (_messages.isEmpty) {
      return;
    }

    await _flutterTts.stop();
    await _flutterTts.speak(_messages[_currentMessageIndex]);
  }

  Future<void> _speakAllMessages() async {
    if (_messages.isEmpty) {
      return;
    }

    await _flutterTts.stop();
    await _flutterTts.speak(_messages.join(' '));
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
    if (_currentMessageIndex >= _messages.length - 1) {
      return;
    }

    setState(() {
      _currentMessageIndex++;
    });

    _speakCurrentMessage();
  }

  Future<void> _forceRefresh() async {
    final position = _currentPosition;

    if (position == null) {
      return;
    }

    await _sendLocationUpdate(position, forceRefresh: true);
  }

  Future<void> _stopDriving({bool closeScreen = true}) async {
    if (_isStoppingDriving) {
      return;
    }

    _isStoppingDriving = true;
    _isDriving = false;

    await _positionSubscription?.cancel();
    _positionSubscription = null;
    await _flutterTts.stop();

    try {
      await http
          .post(
            Uri.parse(stopDrivingUrl),
            headers: const {'Content-Type': 'application/json; charset=UTF-8'},
            body: jsonEncode({}),
          )
          .timeout(const Duration(seconds: 15));
    } catch (_) {
      // 서버가 이미 종료됐더라도 화면과 GPS는 정상적으로 종료합니다.
    }

    if (closeScreen && mounted) {
      Navigator.pop(context);
    }
  }

  Future<bool> _confirmExit() async {
    final shouldExit = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('운전을 종료할까요?'),
        content: const Text('실시간 GPS 전송과 음성 안내가 종료됩니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('계속 운전'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('운전 종료'),
          ),
        ],
      ),
    );

    if (shouldExit == true) {
      await _stopDriving();
      return true;
    }

    return false;
  }

  String get _currentRegionText {
    final region = _currentRegion;

    if (region == null) {
      return '확인 중';
    }

    final sido = _firstValue(region, ['시도', 'sido']);
    final sigungu = _firstValue(region, ['시군구', '시군구명', 'sigungu']);

    final values = <String>[
      if (sido.isNotEmpty) sido,
      if (sigungu.isNotEmpty && sigungu != sido) sigungu,
    ];

    return values.isEmpty ? '확인 중' : values.join(' ');
  }

  @override
  void dispose() {
    _positionSubscription?.cancel();
    _flutterTts.stop();

    if (_isDriving) {
      http.post(
        Uri.parse(stopDrivingUrl),
        headers: const {'Content-Type': 'application/json; charset=UTF-8'},
        body: jsonEncode({}),
      );
    }

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final currentMessage = _messages.isEmpty
        ? '실시간 안내를 기다리고 있습니다.'
        : _messages[_currentMessageIndex];

    final currentLatLng = _currentPosition == null
        ? null
        : LatLng(_currentPosition!.latitude, _currentPosition!.longitude);

    return PopScope(
      canPop: !_isDriving,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop && _isDriving) {
          await _confirmExit();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF101820),
        appBar: AppBar(
          title: const Text('실시간 운전 안내'),
          backgroundColor: const Color(0xFF101820),
          foregroundColor: Colors.white,
          actions: [
            IconButton(
              onPressed:
                  _isDriving && _currentPosition != null && !_isSendingLocation
                  ? _forceRefresh
                  : null,
              tooltip: '교통정보 즉시 갱신',
              icon: _isSendingLocation
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
            ),
          ],
        ),
        body: SafeArea(
          child: _isStartingDriving
              ? const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 20),
                      Text(
                        '실시간 운전 모드를 시작하고 있습니다.',
                        style: TextStyle(color: Colors.white, fontSize: 17),
                      ),
                    ],
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    if (_drivingError != null)
                      Card(
                        color: Colors.red.shade100,
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Text(
                            _drivingError!,
                            style: TextStyle(color: Colors.red.shade900),
                          ),
                        ),
                      ),
                    if (_drivingError != null) const SizedBox(height: 12),
                    if (widget.routePoints.length >= 2)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(18),
                        child: SizedBox(
                          height: 260,
                          child: FlutterMap(
                            mapController: _mapController,
                            options: MapOptions(
                              initialCameraFit: CameraFit.bounds(
                                bounds: LatLngBounds.fromPoints(
                                  widget.routePoints,
                                ),
                                padding: const EdgeInsets.all(32),
                              ),
                            ),
                            children: [
                              TileLayer(
                                urlTemplate:
                                    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                                userAgentPackageName: 'com.example.safe_drive',
                              ),
                              PolylineLayer(
                                polylines: [
                                  Polyline(
                                    points: widget.routePoints,
                                    strokeWidth: 5,
                                    color: const Color(0xFF1D4E89),
                                  ),
                                ],
                              ),
                              MarkerLayer(
                                markers: [
                                  Marker(
                                    point: widget.routePoints.first,
                                    width: 42,
                                    height: 42,
                                    child: const Icon(
                                      Icons.trip_origin,
                                      color: Colors.green,
                                      size: 32,
                                    ),
                                  ),
                                  Marker(
                                    point: widget.routePoints.last,
                                    width: 44,
                                    height: 44,
                                    child: const Icon(
                                      Icons.location_on,
                                      color: Colors.red,
                                      size: 38,
                                    ),
                                  ),
                                  if (currentLatLng != null)
                                    Marker(
                                      point: currentLatLng,
                                      width: 50,
                                      height: 50,
                                      child: Container(
                                        decoration: BoxDecoration(
                                          color: Colors.blue.withValues(
                                            alpha: 0.22,
                                          ),
                                          shape: BoxShape.circle,
                                        ),
                                        child: const Icon(
                                          Icons.navigation,
                                          color: Colors.blue,
                                          size: 32,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              RichAttributionWidget(
                                attributions: const [
                                  TextSourceAttribution(
                                    'OpenStreetMap contributors',
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (widget.routePoints.length >= 2)
                      const SizedBox(height: 16),
                    Card(
                      elevation: 0,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          children: [
                            _LiveStatusRow(
                              icon: Icons.location_city,
                              label: '현재 지역',
                              value: _currentRegionText,
                            ),
                            _LiveStatusRow(
                              icon: Icons.cloud_outlined,
                              label: '현재 날씨',
                              value: '$_currentWeather · $_weatherSource',
                            ),
                            _LiveStatusRow(
                              icon: Icons.speed,
                              label: '현재 속도',
                              value:
                                  '${_currentSpeedKmh.toStringAsFixed(0)}km/h',
                            ),
                            _LiveStatusRow(
                              icon: Icons.route,
                              label: '진행 거리',
                              value: '${_routeProgressKm.toStringAsFixed(1)}km',
                            ),
                            _LiveStatusRow(
                              icon: Icons.flag_outlined,
                              label: '남은 거리',
                              value:
                                  '${_remainingDistanceKm.toStringAsFixed(1)}km',
                            ),
                            _LiveStatusRow(
                              icon: Icons.schedule,
                              label: '남은 시간',
                              value: '${_remainingMinutes.round()}분',
                            ),
                            _LiveStatusRow(
                              icon: Icons.alt_route,
                              label: '경로 이탈 거리',
                              value:
                                  '${_distanceFromRouteM.toStringAsFixed(0)}m',
                            ),
                            _LiveStatusRow(
                              icon: Icons.timer_outlined,
                              label: '연속 운전',
                              value:
                                  '${_continuousDrivingMinutes.toStringAsFixed(1)}분',
                            ),
                            _LiveStatusRow(
                              icon: _isResting
                                  ? Icons.hotel
                                  : Icons.directions_car,
                              label: '운전 상태',
                              value: _isResting ? '휴식 중' : '주행 중',
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Card(
                      color: _restAlert ? Colors.amber.shade100 : Colors.white,
                      elevation: 0,
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Column(
                          children: [
                            Icon(
                              _isSpeaking
                                  ? Icons.volume_up_rounded
                                  : _restAlert
                                  ? Icons.warning_amber_rounded
                                  : Icons.record_voice_over,
                              size: 62,
                              color: _restAlert
                                  ? Colors.orange.shade800
                                  : const Color(0xFF1D4E89),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              currentMessage,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontSize: 20,
                                height: 1.45,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 14),
                            Text(
                              _messages.isEmpty
                                  ? '0 / 0'
                                  : '${_currentMessageIndex + 1} / '
                                        '${_messages.length}',
                              style: const TextStyle(color: Colors.black54),
                            ),
                            const SizedBox(height: 18),
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
                                const SizedBox(width: 12),
                                FilledButton.icon(
                                  onPressed: _messages.isEmpty
                                      ? null
                                      : _speakCurrentMessage,
                                  icon: const Icon(Icons.volume_up),
                                  label: const Text('다시 듣기'),
                                ),
                                const SizedBox(width: 12),
                                IconButton.filledTonal(
                                  onPressed:
                                      _currentMessageIndex <
                                          _messages.length - 1
                                      ? _showNextMessage
                                      : null,
                                  icon: const Icon(Icons.skip_next),
                                  tooltip: '다음 안내',
                                ),
                              ],
                            ),
                            TextButton.icon(
                              onPressed: _messages.isEmpty
                                  ? null
                                  : _speakAllMessages,
                              icon: const Icon(Icons.playlist_play),
                              label: const Text('전체 안내 듣기'),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 18),
                    SizedBox(
                      height: 52,
                      child: FilledButton.icon(
                        onPressed: _isStoppingDriving
                            ? null
                            : () => _confirmExit(),
                        style: FilledButton.styleFrom(
                          backgroundColor: Colors.red.shade700,
                        ),
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: Text(_isStoppingDriving ? '종료 중' : '운전 종료'),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

class _LiveStatusRow extends StatelessWidget {
  const _LiveStatusRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 21, color: const Color(0xFF1D4E89)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(label, style: const TextStyle(color: Colors.black54)),
          ),
          Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}

String _extractServerError(http.Response response, {required String fallback}) {
  try {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));

    if (decoded is Map<String, dynamic>) {
      return decoded['detail']?.toString() ?? fallback;
    }
  } catch (_) {
    // JSON 형식이 아니면 아래 기본 메시지를 사용합니다.
  }

  return '$fallback (HTTP ${response.statusCode})';
}

Future<Position> determineCurrentPosition() async {
  final serviceEnabled = await Geolocator.isLocationServiceEnabled();

  if (!serviceEnabled) {
    throw Exception('기기의 위치 서비스가 꺼져 있습니다.');
  }

  var permission = await Geolocator.checkPermission();

  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }

  if (permission == LocationPermission.denied) {
    throw Exception('위치 권한이 거부되었습니다.');
  }

  if (permission == LocationPermission.deniedForever) {
    throw Exception(
      '위치 권한이 영구적으로 거부되었습니다. '
      '앱 설정에서 위치 권한을 허용하세요.',
    );
  }

  return Geolocator.getCurrentPosition(
    locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
  );
}

Map<String, dynamic> _asStringMap(dynamic value) {
  if (value is Map<String, dynamic>) {
    return value;
  }

  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }

  return <String, dynamic>{};
}

List<Map<String, dynamic>> _asMapList(dynamic value) {
  if (value is! List) {
    return <Map<String, dynamic>>[];
  }

  return value.map(_asStringMap).where((item) => item.isNotEmpty).toList();
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

String _firstValue(Map<String, dynamic> map, List<String> keys) {
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
