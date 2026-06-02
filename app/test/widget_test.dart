import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:harbi_ganyan/widgets/rozet.dart';

void main() {
  testWidgets('TutturmaRozet 6/6 TUTTU gösterir', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: TutturmaRozet(6))),
    );
    expect(find.text('6/6 TUTTU'), findsOneWidget);
  });
}
