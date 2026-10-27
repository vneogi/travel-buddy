import 'package:sqflite/sqflite.dart';

/// Web / default: unencrypted open (SPEC-43 Gap 5 encrypts Android/iOS only).
Future<Database> openOfflineStore(
  String path, {
  required int version,
  required OnDatabaseCreateFn onCreate,
  required OnDatabaseVersionChangeFn onUpgrade,
}) {
  return openDatabase(
    path,
    version: version,
    onCreate: onCreate,
    onUpgrade: onUpgrade,
  );
}
