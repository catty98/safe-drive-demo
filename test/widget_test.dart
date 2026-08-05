import 'package:flutter_test/flutter_test.dart';
import 'package:safe_drive/main.dart';

void main() {
  testWidgets('SAFE DRIVE 초기 화면 표시', (WidgetTester tester) async {
    await tester.pumpWidget(const SafeDriveApp());

    expect(find.text('SAFE DRIVE'), findsOneWidget);
    expect(find.text('안전 경로 분석'), findsWidgets);
  });
}
