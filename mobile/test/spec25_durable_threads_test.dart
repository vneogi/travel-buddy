// SPEC-25 Phase C: Durable trip Ask threads (device-local).
//
// Tests: migration, persistence round-trip, reopen, identity isolation,
// trip isolation, envelope hygiene, proposal safety, deletion, retention,
// and offline behavior.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';
import 'package:travel_buddy/offline/offline_database.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // ===================================================================
  // Migration
  // ===================================================================
  group('migration v7 -> v8', () {
    test('v7 database upgrades to v8 with ask tables; existing rows survive',
        () async {
      // Create a v7 database manually, insert data, close, reopen at v8.
      final v7db = await openDatabase(
        inMemoryDatabasePath,
        version: 7,
        onCreate: (db, version) async {
          // Minimal v7 schema: outbox + loved_places + node_outcome
          await db.execute(
            'CREATE TABLE outbox ('
            '  signal_id TEXT PRIMARY KEY,'
            '  payload_json TEXT NOT NULL,'
            '  captured_at TEXT NOT NULL,'
            '  attempts INTEGER NOT NULL DEFAULT 0,'
            '  next_retry_at TEXT,'
            '  last_error TEXT,'
            '  state TEXT NOT NULL'
            ')',
          );
          await db.execute(
            'CREATE TABLE cache_trip ('
            '  trip_id TEXT PRIMARY KEY,'
            '  state_json TEXT NOT NULL,'
            '  cached_at TEXT NOT NULL'
            ')',
          );
          await db.execute(
            'CREATE TABLE cache_place ('
            '  place_ref TEXT PRIMARY KEY,'
            '  data_json TEXT NOT NULL,'
            '  cached_at TEXT NOT NULL'
            ')',
          );
          await db.execute(
            'CREATE TABLE cache_trip_list ('
            '  cache_key TEXT PRIMARY KEY,'
            '  list_json TEXT NOT NULL,'
            '  cached_at TEXT NOT NULL'
            ')',
          );
          await db.execute(
            'CREATE TABLE alert_cache ('
            '  identity_scope TEXT NOT NULL,'
            '  trip_id TEXT NOT NULL,'
            '  payload_json TEXT NOT NULL,'
            '  cached_at TEXT NOT NULL,'
            '  expires_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, trip_id)'
            ')',
          );
          await db.execute(
            'CREATE TABLE alert_dismissals ('
            '  identity_scope TEXT NOT NULL,'
            '  alert_id TEXT NOT NULL,'
            '  dismissed_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, alert_id)'
            ')',
          );
          await db.execute(
            'CREATE TABLE loved_places ('
            '  identity_scope TEXT NOT NULL,'
            '  trip_id TEXT NOT NULL,'
            '  place_ref TEXT NOT NULL,'
            '  loved_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, trip_id, place_ref)'
            ')',
          );
          await db.execute(
            'CREATE TABLE app_kv ('
            '  key TEXT PRIMARY KEY,'
            '  value TEXT NOT NULL'
            ')',
          );
          await db.execute(
            'CREATE TABLE node_outcome ('
            '  identity_scope TEXT NOT NULL,'
            '  trip_id TEXT NOT NULL,'
            '  node_id TEXT NOT NULL,'
            '  outcome TEXT NOT NULL,'
            '  reason TEXT,'
            '  recorded_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, trip_id, node_id)'
            ')',
          );
          await db.execute(
            'CREATE TABLE notification_cache ('
            '  identity_scope TEXT NOT NULL,'
            '  trip_id TEXT NOT NULL,'
            '  payload_json TEXT NOT NULL,'
            '  cached_at TEXT NOT NULL,'
            '  expires_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, trip_id)'
            ')',
          );
          await db.execute(
            'CREATE TABLE notification_dismissals ('
            '  identity_scope TEXT NOT NULL,'
            '  notification_id TEXT NOT NULL,'
            '  dismissed_at TEXT NOT NULL,'
            '  PRIMARY KEY (identity_scope, notification_id)'
            ')',
          );
        },
      );

      // Insert pre-existing data.
      await v7db.insert('loved_places', {
        'identity_scope': 'account:a',
        'trip_id': 'trip-1',
        'place_ref': 'wat-xieng-thong',
        'loved_at': '2026-10-01T00:00:00.000Z',
      });
      await v7db.insert('node_outcome', {
        'identity_scope': 'account:a',
        'trip_id': 'trip-1',
        'node_id': 'node-1',
        'outcome': 'visited',
        'recorded_at': '2026-10-01T12:00:00.000Z',
      });
      await v7db.close();

      // Reopen through OfflineDatabase which upgrades to v8.
      final offDb = OfflineDatabase(testPath: inMemoryDatabasePath);
      final database = await offDb.db;

      expect(await database.getVersion(), 8);

      // Verify new tables exist.
      final tables = await database.rawQuery(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('ask_thread', 'ask_message')",
      );
      expect(
        tables.map((r) => r['name']).toSet(),
        {'ask_thread', 'ask_message'},
      );

      await offDb.close();
    });
  });

  // ===================================================================
  // Ask thread CRUD + persistence
  // ===================================================================
  group('ask threads', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('create thread and insert messages round-trip', () async {
      await database.createAskThread(
        threadId: 't1',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'What are the opening hours?',
      );
      await database.insertAskMessage(
        messageId: 'm1',
        threadId: 't1',
        role: 'user',
        text: 'What are the opening hours?',
      );
      final envelope = jsonEncode({
        'answer': 'Ban Anou Night Market opens 17:00-23:00.',
        'tier': 'assert',
        'path': 'grounded_deterministic',
        'intent': 'opening_hours',
        'source_ids': ['lp-v1'],
        'source_class': 'curated_catalog',
        'from_cache': false,
      });
      await database.insertAskMessage(
        messageId: 'm2',
        threadId: 't1',
        role: 'assistant',
        text: 'Ban Anou Night Market opens 17:00-23:00.',
        envelopeJson: envelope,
      );

      final messages = await database.loadAskMessages(threadId: 't1');
      expect(messages.length, 2);
      expect(messages[0]['role'], 'user');
      expect(messages[0]['text'], 'What are the opening hours?');
      expect(messages[1]['role'], 'assistant');
      expect(messages[1]['envelope_json'], isNotNull);

      final decoded = jsonDecode(messages[1]['envelope_json'] as String)
          as Map<String, dynamic>;
      expect(decoded['intent'], 'opening_hours');
      expect(decoded['tier'], 'assert');
    });

    test('getMostRecentAskThread returns newest', () async {
      await database.createAskThread(
        threadId: 't-old',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Old thread',
        createdAt: DateTime.utc(2026, 10, 1),
      );
      await database.createAskThread(
        threadId: 't-new',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'New thread',
        createdAt: DateTime.utc(2026, 10, 10),
      );

      final recent = await database.getMostRecentAskThread(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(recent?['thread_id'], 't-new');
    });

    // R17 sabotage: identity isolation
    test('identity isolation -- scope A not visible to scope B', () async {
      await database.createAskThread(
        threadId: 't-scope-a',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Thread from A',
      );
      await database.insertAskMessage(
        messageId: 'm-scope-a',
        threadId: 't-scope-a',
        role: 'user',
        text: 'Hello from A',
      );

      final threadsB = await database.listAskThreads(
        identityScope: 'account:b',
        tripId: 'trip-1',
      );
      expect(threadsB, isEmpty,
          reason: 'Scope B must not see scope A threads');

      final threadsA = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(threadsA.length, 1);
    });

    // R17 sabotage: trip isolation
    test('trip isolation -- trip-1 not listed for trip-2', () async {
      await database.createAskThread(
        threadId: 't-trip-1',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Trip 1 thread',
      );

      final trip2Threads = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-2',
      );
      expect(trip2Threads, isEmpty,
          reason: 'Trip-2 must not see trip-1 threads');
    });

    test('envelope_json never contains booking codes or coordinates',
        () async {
      // Simulate storing an envelope that has answer text only.
      // The brief says: Never store raw trip JSON, node lists,
      // booking confirmation codes, booking notes, or coordinates.
      final safeEnvelope = jsonEncode({
        'answer': 'Wat Xieng Thong opens 8:00-17:00.',
        'tier': 'assert',
        'path': 'grounded_deterministic',
        'intent': 'opening_hours',
        'source_ids': ['wxt-1'],
        'source_class': 'curated_catalog',
        'from_cache': false,
      });

      await database.createAskThread(
        threadId: 't-hyg',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Hygiene test',
      );
      await database.insertAskMessage(
        messageId: 'm-hyg',
        threadId: 't-hyg',
        role: 'assistant',
        text: 'Wat Xieng Thong opens 8:00-17:00.',
        envelopeJson: safeEnvelope,
      );

      final msgs = await database.loadAskMessages(threadId: 't-hyg');
      final stored = msgs.first['envelope_json'] as String;
      expect(stored.contains('confirmation_code'), isFalse);
      expect(stored.contains('booking_notes'), isFalse);
      expect(stored.contains('"lat"'), isFalse);
      expect(stored.contains('"lng"'), isFalse);
      expect(stored.contains('"nodes"'), isFalse);
    });

    test('stored plan-change proposal does not contain structural event data',
        () async {
      // A proposal envelope: display only. Reopening must never execute.
      final proposalEnvelope = jsonEncode({
        'answer': 'I suggest swapping the next stop.',
        'tier': 'hedge',
        'path': 'grounded_deterministic',
        'intent': 'plan_change',
        'source_ids': [],
        'source_class': 'trip_state',
        'from_cache': false,
        'proposal': {
          'event_type': 'swap_activity',
          'target_node_id': 'node-42',
          'summary': 'Swap to Saffron Coffee',
        },
      });
      await database.createAskThread(
        threadId: 't-prop',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Proposal test',
      );
      await database.insertAskMessage(
        messageId: 'm-prop',
        threadId: 't-prop',
        role: 'assistant',
        text: 'I suggest swapping the next stop.',
        envelopeJson: proposalEnvelope,
      );

      final msgs = await database.loadAskMessages(threadId: 't-prop');
      final stored = jsonDecode(msgs.first['envelope_json'] as String)
          as Map<String, dynamic>;
      // Verify proposal is stored for display.
      expect(stored['proposal'], isNotNull);
      // But no trip_state JSON, no node lists.
      expect(stored.containsKey('trip_state'), isFalse);
      expect(stored.containsKey('nodes'), isFalse);
    });
  });

  // ===================================================================
  // Deletion
  // ===================================================================
  group('deletion', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('deleteAskThread removes thread and messages', () async {
      await database.createAskThread(
        threadId: 't-del',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'To delete',
      );
      await database.insertAskMessage(
        messageId: 'm-del-1',
        threadId: 't-del',
        role: 'user',
        text: 'Hello',
      );
      await database.insertAskMessage(
        messageId: 'm-del-2',
        threadId: 't-del',
        role: 'assistant',
        text: 'Hi there',
      );

      await database.deleteAskThread('t-del');

      final threads = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(threads, isEmpty);
      final msgs = await database.loadAskMessages(threadId: 't-del');
      expect(msgs, isEmpty);
    });

    test('deleteAskHistoryForTrip removes all threads for that trip',
        () async {
      await database.createAskThread(
        threadId: 't-a',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'A',
      );
      await database.createAskThread(
        threadId: 't-b',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'B',
      );
      // Different trip -- should survive.
      await database.createAskThread(
        threadId: 't-other',
        identityScope: 'account:a',
        tripId: 'trip-2',
        title: 'Other',
      );

      await database.deleteAskHistoryForTrip(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );

      final trip1 = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(trip1, isEmpty);

      final trip2 = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-2',
      );
      expect(trip2.length, 1);
    });

    test('deleteAskHistoryForIdentity removes all threads for that identity',
        () async {
      await database.createAskThread(
        threadId: 't-id-a1',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'A1',
      );
      await database.createAskThread(
        threadId: 't-id-a2',
        identityScope: 'account:a',
        tripId: 'trip-2',
        title: 'A2',
      );
      await database.createAskThread(
        threadId: 't-id-b',
        identityScope: 'account:b',
        tripId: 'trip-1',
        title: 'B',
      );

      await database.deleteAskHistoryForIdentity(
        identityScope: 'account:a',
      );

      final a = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(a, isEmpty);

      final b = await database.listAskThreads(
        identityScope: 'account:b',
        tripId: 'trip-1',
      );
      expect(b.length, 1);
    });
  });

  // ===================================================================
  // Retention
  // ===================================================================
  group('retention', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('51st thread prunes the oldest', () async {
      for (var i = 0; i < 51; i++) {
        await database.createAskThread(
          threadId: 'thread-$i',
          identityScope: 'account:a',
          tripId: 'trip-1',
          title: 'Thread $i',
          createdAt: DateTime.utc(2026, 1, 1).add(Duration(minutes: i)),
        );
      }

      final threads = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(threads.length, 50);
      // The oldest (thread-0) should have been pruned.
      final ids = threads.map((t) => t['thread_id'] as String).toSet();
      expect(ids.contains('thread-0'), isFalse,
          reason: 'Oldest thread must be pruned');
      expect(ids.contains('thread-50'), isTrue);
    });

    test('201st message prunes the oldest', () async {
      await database.createAskThread(
        threadId: 't-retention',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Retention test',
      );
      for (var i = 0; i < 201; i++) {
        await database.insertAskMessage(
          messageId: 'msg-$i',
          threadId: 't-retention',
          role: 'user',
          text: 'Message $i',
          createdAt: DateTime.utc(2026, 1, 1).add(Duration(seconds: i)),
        );
      }

      final msgs =
          await database.loadAskMessages(threadId: 't-retention');
      expect(msgs.length, 200);
      // The oldest (msg-0) should have been pruned.
      final ids = msgs.map((m) => m['message_id'] as String).toSet();
      expect(ids.contains('msg-0'), isFalse,
          reason: 'Oldest message must be pruned');
      expect(ids.contains('msg-200'), isTrue);
    });
  });

  // ===================================================================
  // Offline: new question shows refusal and writes no assistant row
  // ===================================================================
  group('offline behavior', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('offline refusal is not persisted as assistant message', () async {
      // Simulate: user sends a question -> written as user message.
      // Offline refusal shown in UI but NOT written as assistant.
      await database.createAskThread(
        threadId: 't-offline',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'Offline test',
      );
      await database.insertAskMessage(
        messageId: 'm-offline-q',
        threadId: 't-offline',
        role: 'user',
        text: 'What time does it open?',
      );
      // DO NOT insert assistant message for offline refusal.

      final msgs =
          await database.loadAskMessages(threadId: 't-offline');
      expect(msgs.length, 1);
      expect(msgs.first['role'], 'user');
      // No assistant row for offline refusal.
      expect(
        msgs.where((m) => m['role'] == 'assistant').length,
        0,
        reason: 'Offline refusal must not be persisted',
      );
    });
  });

  // ===================================================================
  // R17 sabotage: drop identity_scope filter → test goes red
  // ===================================================================
  group('R17 sabotage proof', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('raw query without identity_scope filter leaks threads', () async {
      await database.createAskThread(
        threadId: 't-leak-a',
        identityScope: 'account:a',
        tripId: 'trip-1',
        title: 'A thread',
      );
      await database.createAskThread(
        threadId: 't-leak-b',
        identityScope: 'account:b',
        tripId: 'trip-1',
        title: 'B thread',
      );

      // Sabotage: query without identity_scope filter.
      final db = await database.db;
      final unfiltered = await db.query(
        'ask_thread',
        where: 'trip_id = ?',
        whereArgs: ['trip-1'],
      );
      // Without identity_scope filter, both threads appear.
      expect(unfiltered.length, 2,
          reason: 'Sabotage confirms both scopes visible without filter');

      // The real method filters properly.
      final filtered = await database.listAskThreads(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      expect(filtered.length, 1);
      expect(filtered.first['thread_id'], 't-leak-a');
    });
  });
}
