import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';

class AiConsultantScreen extends StatefulWidget {
  const AiConsultantScreen({super.key});

  @override
  State<AiConsultantScreen> createState() => _AiConsultantScreenState();
}

class _AiConsultantScreenState extends State<AiConsultantScreen> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 80,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    _messageController.clear();
    final appState = Provider.of<AppState>(context, listen: false);
    
    await appState.sendAiMessage(text);
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final history = appState.chatHistory;
    final isLoading = appState.isLoading;

    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            // Screen Header title
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: AppTheme.primaryGradient,
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.primary.withOpacity(0.3),
                          blurRadius: 8,
                        )
                      ]
                    ),
                    child: const Icon(Icons.android_rounded, color: Colors.white, size: 24),
                  ),
                  const SizedBox(width: 12),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'ИИ-Консультант',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                      ),
                      Text(
                        'Всегда на связи',
                        style: TextStyle(color: AppTheme.income, fontSize: 11, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const Divider(color: AppTheme.border, height: 1),

            // Chat Messages List
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.all(20),
                itemCount: history.length + (isLoading ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == history.length) {
                    // Typing loader
                    return _buildLoadingBubble();
                  }

                  final msg = history[index];
                  return _buildChatBubble(msg);
                },
              ),
            ),

            // Input Send Row
            Container(
              padding: const EdgeInsets.all(12),
              decoration: const BoxDecoration(
                color: AppTheme.surface,
                border: Border(
                  top: BorderSide(color: AppTheme.border, width: 1),
                ),
              ),
              child: Row(
                children: [
                  // Text message input field
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                        color: AppTheme.surfaceCard,
                        borderRadius: BorderRadius.circular(24),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: TextField(
                        controller: _messageController,
                        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15),
                        textInputAction: TextInputAction.send,
                        onSubmitted: (_) => _sendMessage(),
                        decoration: const InputDecoration(
                          hintText: 'Спросите про расходы, баланс...',
                          hintStyle: TextStyle(color: Colors.white24, fontSize: 14),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),

                  // Send Action Button
                  GestureDetector(
                    onTap: _sendMessage,
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: AppTheme.primaryGradient,
                      ),
                      child: const Icon(
                        Icons.send_rounded,
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChatBubble(ChatMessage msg) {
    return Align(
      alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: msg.isUser
            ? BoxDecoration(
                gradient: AppTheme.primaryGradient,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                  bottomLeft: Radius.circular(16),
                ),
              )
            : AppTheme.glassCardDecoration(
                color: AppTheme.surfaceCard.withOpacity(0.9),
                radius: 16,
              ).copyWith(
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                ),
              ),
        child: Text(
          msg.text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 14,
            height: 1.3,
          ),
        ),
      ),
    );
  }

  Widget _buildLoadingBubble() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: AppTheme.glassCardDecoration(
          color: AppTheme.surfaceCard.withOpacity(0.9),
          radius: 16,
        ).copyWith(
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomRight: Radius.circular(16),
          ),
        ),
        child: const SpinKitThreeBounce(
          color: AppTheme.secondary,
          size: 18,
        ),
      ),
    );
  }
}
