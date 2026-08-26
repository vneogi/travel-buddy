import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

/// Web initialization: IndexedDB-backed SQLite via Wasm.
void initDatabaseFactory() {
  databaseFactory = databaseFactoryFfiWeb;
}
