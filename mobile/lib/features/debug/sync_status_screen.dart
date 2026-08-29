import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../offline/sync_engine.dart';

/// Extracted helper: reset auth halt, await sync, then read counts.
/// Testable without pumping the widget tree.
Future<Map<String, int>> refreshSyncStatus(SyncEngine engine) async {
  engine.resetAuthHalted();
  await engine.syncOnce();
  return engine.getStatusCounts();
}

/// Sync status debug screen (SPEC-02 B.5).
///
/// Shows: pending / inflight / failed_permanent counts,
/// last sync time, last error. Trip-critical for Laos field test —
/// answers 'is my data actually reaching the server?' without a laptop.
class SyncStatusScreen extends ConsumerStatefulWidget {
  const SyncStatusScreen({super.key});

  @override
  ConsumerState<SyncStatusScreen> createState() => _SyncStatusScreenState();
}

class _SyncStatusScreenState extends ConsumerState<SyncStatusScreen> {
  Map<String, int> _counts = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    final result = await refreshSyncStatus(ref.read(syncEngineProvider));
    if (mounted) {
      setState(() {
        _counts = result;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final syncEngine = ref.watch(syncEngineProvider);
    final lastSync = syncEngine.lastSyncTime;
    final lastError = syncEngine.lastError;
    final isSyncing = syncEngine.isSyncing;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sync Status'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refresh,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _StatusCard(
                  title: 'Sync Engine',
                  status: isSyncing ? 'SYNCING...' : 'IDLE',
                  color: isSyncing ? Colors.blue : Colors.green,
                ),
                if (syncEngine.authHalted)
                  const _StatusCard(
                    title: 'Auth Status',
                    status: 'HALTED (401)',
                    color: Colors.red,
                  ),
                const SizedBox(height: 12),
                _CountCard(
                  label: 'Pending',
                  count: _counts['pending'] ?? 0,
                  icon: Icons.schedule,
                  color: Colors.orange,
                ),
                _CountCard(
                  label: 'Inflight',
                  count: _counts['inflight'] ?? 0,
                  icon: Icons.cloud_upload,
                  color: Colors.blue,
                ),
                _CountCard(
                  label: 'Failed (permanent)',
                  count: _counts['failed_permanent'] ?? 0,
                  icon: Icons.error_outline,
                  color: Colors.red,
                ),
                const Divider(height: 32),
                ListTile(
                  leading: const Icon(Icons.access_time),
                  title: const Text('Last sync'),
                  subtitle: Text(
                    lastSync?.toIso8601String() ?? 'Never',
                  ),
                ),
                if (lastError != null) ...[
                  ListTile(
                    leading: const Icon(Icons.warning, color: Colors.amber),
                    title: const Text('Last error'),
                    subtitle: Text(
                      lastError,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                const Divider(height: 32),
                ElevatedButton.icon(
                  onPressed: () {
                    ref.read(syncEngineProvider).triggerSync();
                    Future.delayed(
                      const Duration(seconds: 2),
                      _refresh,
                    );
                  },
                  icon: const Icon(Icons.sync),
                  label: const Text('Force sync now'),
                ),
              ],
            ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final String title;
  final String status;
  final Color color;

  const _StatusCard({
    required this.title,
    required this.status,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(title),
        trailing: Chip(
          label: Text(status, style: const TextStyle(color: Colors.white)),
          backgroundColor: color,
        ),
      ),
    );
  }
}

class _CountCard extends StatelessWidget {
  final String label;
  final int count;
  final IconData icon;
  final Color color;

  const _CountCard({
    required this.label,
    required this.count,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(label),
        trailing: Text(
          count.toString(),
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: color),
        ),
      ),
    );
  }
}
