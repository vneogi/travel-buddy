// SPEC-43 Gap 12: Ask question text must not appear in the route URI.
//
// Tiny GoRouter only. No ChatScreen, ItineraryScreen, SQLite, or Riverpod.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:travel_buddy/routing/chat_route.dart';

const _tripId = 'trip-7f3a';
const _question = 'secret ask about hidden courtyard';

class _Recorded {
  Uri? uri;
  Object? extra;
  String? initialQuestion;
}

GoRouter _router(_Recorded rec) => GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (_, __) => const SizedBox()),
        GoRoute(
          path: '/trip/:tripId/chat',
          builder: (_, state) {
            rec.uri = state.uri;
            rec.extra = state.extra;
            rec.initialQuestion = chatInitialQuestionFromExtra(state.extra);
            return const SizedBox();
          },
        ),
      ],
    );

Future<GoRouter> _mount(WidgetTester tester, _Recorded rec) async {
  final router = _router(rec);
  addTearDown(router.dispose);
  await tester.pumpWidget(
    WidgetsApp.router(
      routerConfig: router,
      color: const Color(0xFF000000),
    ),
  );
  await tester.pump();
  return router;
}

void main() {
  testWidgets('test_chat_question_is_not_in_route_uri', (tester) async {
    final rec = _Recorded();
    final router = await _mount(tester, rec);

    router.push(
      chatRoutePath(_tripId),
      extra: const ChatRouteExtra(initialQuestion: _question),
    );
    await tester.pump();

    final uri = rec.uri!;
    expect(uri.path, '/trip/$_tripId/chat');
    expect(uri.queryParameters, isEmpty);
    expect(uri.hasQuery, isFalse);
    final location = uri.toString();
    expect(location, isNot(contains(_question)));
    expect(location, isNot(contains(Uri.encodeQueryComponent(_question))));
    expect(location, isNot(contains(Uri.encodeComponent(_question))));
    expect(location, isNot(contains('hidden')));
    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      isNot(contains('hidden')),
    );

    expect(rec.extra, isA<ChatRouteExtra>());
    expect((rec.extra as ChatRouteExtra).initialQuestion, _question);
    expect(rec.initialQuestion, _question);
  });

  testWidgets('legacy ?q= link does not seed the chat question',
      (tester) async {
    final rec = _Recorded();
    final router = await _mount(tester, rec);

    router.go(
      '/trip/$_tripId/chat?q=${Uri.encodeQueryComponent(_question)}',
    );
    await tester.pump();

    expect(rec.uri!.path, '/trip/$_tripId/chat');
    expect(rec.extra, isNull);
    expect(rec.initialQuestion, isNull);
  });

  test('wrong-type extra yields no initial question', () {
    expect(chatInitialQuestionFromExtra(null), isNull);
    expect(chatInitialQuestionFromExtra(_question), isNull);
    expect(chatInitialQuestionFromExtra({'q': _question}), isNull);
  });

  test('chatRoutePath has no query string', () {
    expect(chatRoutePath(_tripId), '/trip/$_tripId/chat');
    expect(Uri.parse(chatRoutePath(_tripId)).hasQuery, isFalse);
  });
}
